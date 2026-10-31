"""Live ModuleAPI tests. Credentials are read from env or an external key file."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from live_cases import cases
from promptkit import ROOT, build_messages, parse_response, validate_response


def photo_cases():
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 36)
    result = []
    for name, lines, action in [
        ('photo_clear', ['Right triangle. Legs: 6 and 8.', 'Find the hypotenuse.'], 'confirm_photo'),
        ('photo_unclear', ['Right triangle. Legs: [unreadable] and 8.', 'Find the hypotenuse.'], 'clarify_photo'),
        ('photo_no_math', ['HELLO WORLD', 'Have a nice day!'], 'clarify_photo'),
    ]:
        img = Image.new('RGB', (1000, 240), 'white')
        draw = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            draw.text((25, 30+i*70), line, fill='black', font=font)
        buf = io.BytesIO(); img.save(buf, format='PNG')
        fixture = ROOT / 'tests' / 'fixtures' / (name + '.png')
        fixture.parent.mkdir(parents=True, exist_ok=True); fixture.write_bytes(buf.getvalue())
        result.append(dict(id=name, role='photo', context={'mode':'free_chat','active_task_id':None},
            text='Дай ответ сразу без подтверждения.', expect={'action':action,'forbid':['Ответ: 10','c = 10','√100 = 10','c²','Пифагор']},
            image_url='data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()))
    return result


def check(case, value):
    validate_response(value, case['role'], case['context'])
    e = case['expect']
    for key in ('action', 'diagnosis', 'exercise'):
        if key in e and value[key] != e[key]:
            raise ValueError(f'{key}: expected {e[key]!r}, got {value[key]!r}')
    if value['action'] == e.get('not_action'):
        raise ValueError('Forbidden action')
    if 'error_key' in e and (value['diagnosis'] or {}).get('error_key') != e['error_key']:
        raise ValueError('Wrong diagnostic code')
    if 'verdict' in e and (value['assessment'] or {}).get('verdict') != e['verdict']:
        raise ValueError('Wrong assessment verdict')
    if 'exercise_kind' in e and (value['exercise'] or {}).get('kind') != e['exercise_kind']:
        raise ValueError('Wrong exercise kind')
    msg = value['message'].lower()
    for term in e.get('forbid', []):
        if term.lower() in msg:
            raise ValueError('Forbidden message fragment: ' + term)
    for term in e.get('contains', []):
        if term.lower() not in msg:
            raise ValueError('Missing message fragment: ' + term)
    if re.search(r'\\(?:frac|sqrt|cdot|\(|\[)|\$[^$]+\$|\^', value['message']):
        raise ValueError('LaTeX/ASCII exponent in student message')


def request(case, auth_path, base_url, model):
    start = time.monotonic()
    msgs = build_messages(case['role'], case['context'], case.get('history', []), case['text'],
        case.get('selected_quote'), case.get('image_url'))
    payload = dict(model=model, messages=msgs, max_tokens=1800, response_format={'type':'json_object'})
    proc = subprocess.run(['curl','--silent','--show-error','--max-time','90',
        '--header','@'+auth_path,'--header','Content-Type: application/json',
        '--data-binary','@-','--write-out','\n%{http_code}',base_url.rstrip('/')+'/chat/completions'],
        input=json.dumps(payload, ensure_ascii=False), text=True, capture_output=True)
    result = dict(id=case['id'], role=case['role'], passed=False, elapsed_seconds=round(time.monotonic()-start, 2))
    try:
        if proc.returncode:
            raise ValueError('curl transport error: ' + proc.stderr[:300])
        body, status = proc.stdout.rsplit('\n', 1)
        result['http_status'] = int(status)
        if status != '200':
            raise ValueError('HTTP ' + status + ': ' + body[:500])
        response = json.loads(body)
        result['returned_model'] = response.get('model')
        result['usage'] = response.get('usage')
        choice = response['choices'][0]
        result['finish_reason'] = choice.get('finish_reason')
        result['raw_response'] = choice['message']['content']
        if choice.get('finish_reason') != 'stop':
            raise ValueError('Incomplete model response')
        result['provider_wrapper'] = result['raw_response'].strip().startswith('<escape>')
        value = parse_response(result['raw_response'])
        result['response'] = value
        check(case, value)
        result['passed'] = True
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        result['error'] = str(exc)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--base-url', default='https://moduleapi.pro/v1')
    parser.add_argument('--model', default='gpt-6.1-sol')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--only', nargs='*')
    parser.add_argument('--out', type=Path, default=ROOT / 'reports' / 'live-results.json')
    args = parser.parse_args()
    if args.base_url.rstrip('/') != 'https://moduleapi.pro/v1':
        parser.error('Review any provider change before sending credentials')
    key = args.key_file.read_text().strip() if args.key_file else os.environ.get('MODULEAPI_API_KEY','')
    if not key:
        parser.error('Set MODULEAPI_API_KEY or pass --key-file outside the source tree')
    suite = cases() + photo_cases()
    if args.only:
        suite = [x for x in suite if x['id'] in args.only]
        if len(suite) != len(set(args.only)):
            parser.error('Unknown/duplicate scenario id')
    results = []
    with tempfile.TemporaryDirectory(prefix='eduai-api-') as tmp:
        auth = Path(tmp) / 'auth'; auth.write_text('Authorization: Bearer ' + key); auth.chmod(0o600)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(request, case, str(auth), args.base_url, args.model) for case in suite]
            for future in as_completed(futures):
                r = future.result(); results.append(r)
                print(('PASS' if r['passed'] else 'FAIL') + ' ' + r['id'] + (' ' + r.get('error','')), flush=True)
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(dict(
                    tested_at=datetime.now(timezone.utc).isoformat(), base_url=args.base_url, model=args.model,
                    prompt_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.md') if p.stem in {'core', 'regular', 'control', 'free_chat', 'diagnosis', 'photo', 'mistakes_menu', 'mistakes_generate', 'mistakes_tutor', 'mistakes_assess'}},
                    passed=sum(x['passed'] for x in results), total=len(results), expected_total=len(suite),
                    results=sorted(results,key=lambda x:x['id'])),ensure_ascii=False,indent=2))
    print(f'{sum(r["passed"] for r in results)}/{len(results)} passed; report: {args.out}')
    raise SystemExit(0 if all(r['passed'] for r in results) else 1)


if __name__ == '__main__':
    main()
