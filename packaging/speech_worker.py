"""Small JSON/stdout boundary for the separately installed speech runtime."""
import asyncio
import json
from pathlib import Path
import sys


def main():
    action = sys.argv[1]
    if action == 'speak':
        import edge_tts
        data = json.loads(sys.stdin.read())
        async def speak():
            chunks = []
            async for chunk in edge_tts.Communicate(data['text'], data['voice'], rate=data['rate'], pitch=data['pitch']).stream():
                if chunk['type'] == 'audio':
                    chunks.append(chunk['data'])
            sys.stdout.buffer.write(b''.join(chunks))
        asyncio.run(speak())
        return
    from faster_whisper import WhisperModel
    name, root = sys.argv[2:4]
    if name not in ('tiny', 'base', 'small'):
        raise ValueError('Unsupported speech model')
    model = WhisperModel(name, device='cpu', compute_type='int8', download_root=root,
                         local_files_only=action != 'download')
    if action == 'download':
        Path(root).mkdir(parents=True, exist_ok=True)
        (Path(root) / (name + '.ready')).write_text('verified', encoding='utf-8')
        print(json.dumps({'ok': True}))
    elif action == 'transcribe':
        segments, _ = model.transcribe(sys.argv[4], language=sys.argv[5] or None,
                                       vad_filter=True, beam_size=1, condition_on_previous_text=False)
        print(json.dumps({'text': ' '.join(s.text.strip() for s in segments).strip()}))
    else:
        raise ValueError('Unknown operation')


if __name__ == '__main__':
    main()
