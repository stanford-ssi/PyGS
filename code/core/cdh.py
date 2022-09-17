from secrets import secrets
import asyncio

PASS = secrets['pass']

commands = {
    'no-op': b'\x8eb',
    'hreset': b'\xd4\x9f',
    'shutdown': b'\x12\x06',
    'query': b'8\x93',
    'exec_cmd': b'\x96\xa2',
    'send_file': b'\x48\x6f',
}

FILENAME = 'img0021.jpg'

def command_handler(gs, payload) -> None:
    
    split = payload.split(' ', 1)
    cmd = split[0]
    msg = PASS

    if cmd == 'shutdown':
        msg += b'\x0b\xfdI\xec' # shutdown confirmation code
    elif cmd == 'query':
        msg += b'cubesat.f_deployed'
    elif cmd == 'exec_cmd':
        msg += b'a=1\nprint(a)'
    elif cmd == 'send_file':
        msg += FILENAME
        asyncio.run(gs.send_file(msg, FILENAME))
        
    
