import logging

import pinylib

log = logging.getLogger(__name__)


def main():
    room_name = raw_input('Enter room name: ').strip()
    if pinylib.CONFIG.ACCOUNT and pinylib.CONFIG.PASSWORD:
        client = pinylib.TinychatRTMPClient(roomname=room_name, account=pinylib.CONFIG.ACCOUNT,
                                            password=pinylib.CONFIG.PASSWORD)
    else:
        client = pinylib.TinychatRTMPClient(roomname=room_name)
    client.nickname = raw_input('Enter nick name (optional): ').strip()

    do_login = raw_input('Login? [enter=No] ')
    if do_login:
        if not client.account:
            client.account = raw_input('Account: ').strip()
        if not client.password:
            client.password = raw_input('Password: ')

        is_logged_in = client.login()
        while not is_logged_in:
            client.account = raw_input('Account: ').strip()
            client.password = raw_input('Password: ')
            if client.account == '/' or client.password == '/':
                main()
                break
            elif client.account == '//' or client.password == '//':
                do_login = False
                break
            else:
                is_logged_in = client.login()
        if is_logged_in:
            client.console_write(pinylib.COLOR['bright_green'], 'Logged in as: %s' % client.account)
    if not do_login:
        client.account = ''
        client.password = None

    status = client.get_rtmp_parameters()
    while True:
        if status == 1:
            client.console_write(pinylib.COLOR['bright_red'], 'Password protected. Enter room password')
            client.room_pass = raw_input()
            if client.room_pass == '/':
                main()
                break
            else:
                status = client.get_rtmp_parameters()
        elif status == 2:
            client.console_write(pinylib.COLOR['bright_red'], 'The room has been closed.')
            main()
            break
        elif status == 4:
            client.console_write(pinylib.COLOR['bright_red'], 'The response returned nothing.')
            main()
            break
        else:
            client.console_write(pinylib.COLOR['bright_green'], 'Connect parameters set.')
            break

    t = pinylib.threading.Thread(target=client.connect)
    t.daemon = True
    t.start()

    while not client.is_connected:
        pinylib.time.sleep(2)
    while client.is_connected:
        chat_msg = raw_input()
        if chat_msg.startswith('/'):
            msg_parts = chat_msg.split(' ')
            cmd = msg_parts[0].lower().strip()
            if cmd == '/q':
                client.disconnect()
            elif cmd == '/a':
                if len(client.users.signed_in) is 0:
                    print ('No signed in users in the room.')
                else:
                    for user in client.users.signed_in:
                        print ('%s:%s' % (user.nick, user.account))
            elif cmd == '/u':
                for user in client.users.all:
                    print ('%s: %s' % (user, client.users.all[user].user_level))
            elif cmd == '/m':
                if len(client.users.mods) is 0:
                    print ('No moderators in the room.')
                else:
                    for mod in client.users.mods:
                        print (mod.nick)
            elif cmd == '/n':
                if len(client.users.norms) is 0:
                    print ('No normal users in the room.')
                else:
                    for norm in client.users.norms:
                        print (norm.nick)
            elif cmd == '/l':
                if len(client.users.lurkers) is 0:
                    print ('No lurkers in the room.')
                else:
                    for lurker in client.users.lurkers:
                        print (lurker.nick)
        else:
            client.send_chat_msg(chat_msg)


if __name__ == '__main__':
    if pinylib.CONFIG.DEBUG_TO_FILE:
        formater = '%(asctime)s : %(levelname)s : %(filename)s : %(lineno)d : %(funcName)s() : %(name)s : %(message)s'
        logging.basicConfig(filename=pinylib.CONFIG.DEBUG_FILE_NAME,
                            level=pinylib.CONFIG.DEBUG_LEVEL, format=formater)
        log.info('Starting pinylib version: %s' % pinylib.__version__)
    else:
        log.addHandler(logging.NullHandler())
    main()
