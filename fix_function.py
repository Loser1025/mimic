
import re

path = r'C:\Users\Loser\Desktop\-\-\unilive\voice_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Define the entire receive_loop function with correct indentation
# Based on the structure: run_voice_mode (0) -> async def receive_loop (16) -> while (20) -> async for (24) -> if (28)
receive_loop_code = r'''                async def receive_loop():
                    _ai_buf: list[str] = []
                    _turn = 0
                    while True:
                        _turn += 1
                        safe_print(C.gray(f"  [DBG] receive: ターン{_turn} 待機開始"), flush=True)
                        _got_turn_complete = False
                        async for response in session.receive():
                            safe_print(C.gray(f"  [DBG] recv t{_turn}: sc={bool(response.server_content)} tool={bool(response.tool_call)} repr={repr(response)[:120].replace(chr(10),' ')}"), flush=True)

                            if response.tool_call:
                                await handle_tool_calls(session, response.tool_call, executor)
                                continue

                            sc = response.server_content
                            if not sc:
                                continue

                            if sc.model_turn:
                                for part in (sc.model_turn.parts or []):
                                    idata = getattr(part, "inline_data", None)
                                    if idata and getattr(idata, "data", None):
                                        audio_out_q.put(idata.data)

                            it = getattr(sc, "input_transcription", None)
                            if it:
                                t = getattr(it, "text", "").strip()
                                if t:
                                    _cur_user.append(t)

                            ot = getattr(sc, "output_transcription", None)
                            if ot:
                                t = getattr(ot, "text", "")
                                if t:
                                    _ai_buf.append(t)
                                    _cur_ai.append(t)

                            if getattr(sc, "turn_complete", False):
                                _got_turn_complete = True
                                user_text = "".join(_cur_user).strip()
                                ai_text   = "".join(_ai_buf).strip()
                                if user_text:
                                    safe_print(C.gray(f"\n  [あなた] {user_text}"), flush=True)
                                if ai_text:
                                    safe_print(f"  {C.bold_purple('[AI]')} {ai_text}", flush=True)
                                if user_text and ai_text and len(executor.react_log.entries) > 0:
                                    executor.post_task(user_text, "".join(_cur_ai), [])
                                _cur_user.clear()
                                _cur_ai.clear()
                                _ai_buf.clear()
                                break
                        if _got_turn_complete:
                            safe_print(C.gray(f"  [DBG] receive: ターン{_turn} 完了→次のターンへ"), flush=True)
                            await asyncio.sleep(0)
                            continue
                        else:
                            safe_print(C.yellow(f"  [DBG] receive: ターン{_turn} ジェネレータ終了（turn_completeなし）→ 再接続"), flush=True)
                            break
'''

# Use regex to replace the entire function block
# Find from 'async def receive_loop():' until the end of its block (before await asyncio.gather)
pattern = r'async def receive_loop\(\):.*?break\n\s+await asyncio\.gather'
# Wait, the pattern needs to be more robust. I'll find 'async def receive_loop():' and the matching 'break' before 'await asyncio.gather'
# Since the function is logically distinct, I'll use a simpler approach: replace from 'async def receive_loop():' up to the line before 'await asyncio.gather(send_loop(), receive_loop())'

# Let's try a more precise regex.
import re
# find the start and end indices
start_match = re.search(r'async def receive_loop\(\):', content)
end_match = re.search(r'await asyncio\.gather\(send_loop\(\), receive_loop\(\)\)', content)

if start_match and end_match:
    start_idx = start_match.start()
    end_idx = end_match.start()
    new_content = content[:start_idx] + receive_loop_code + content[end_idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully replaced receive_loop function.")
else:
    print("Could not find function boundaries.")
