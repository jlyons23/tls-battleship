#!/usr/bin/env python3
import socket
import argparse
import ssl
from ssl import TLSVersion
import sys
import hashlib
import json


# Set constants for connection and game
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 12345
FORMAT = 'utf-8'
SHIP_TOTAL = 14
# Colour codes
RED   = '\033[31m'
CYAN  = '\033[36m'
RESET = '\033[0m'


def read_message(conn):
    """
    Reads data in one byte increments until a newline character is found.
    Returns the string decoded and stripped.
    Returns None when connection drops.
    """
    data = b''
    max_len = 512
    while not data.endswith(b'\n'):
        if len(data) >= max_len:
            # Too many bytes without a newline 
            print("Protocol error: incoming line too long. Disconnecting.")
            return None
        try:
            char = conn.recv(1)
            if not char:
                return None
            data += char
        except socket.timeout:
            print("Server timed out. Exiting.")
            return None
    return data.decode(FORMAT).rstrip('\r\n')

def valid_shot(coords):
    """
    Validates the shot coordinates.
    """
    return len(coords) == 2 and coords[0] in 'ABCDEFGHI' and coords[1] in '123456789'

def coords_to_index(coords):
    """
    Converts shot coordinates from letter number to row column.
    """
    column = ord(coords[0]) - ord('A')
    row = int(coords[1]) - 1
    return (row, column)

def create_board():
    """
    Creates and returns an empty 9x9 board.
    """
    board = [["." for _ in range(9)] for _ in range(9)]
    return board

def color_cell(c):
    """
    Colours hits and misses to improve UI.
    """
    if c == 'X':   
        return f"{RED}X{RESET}"
    if c == 'o':   
        return f"{CYAN}o{RESET}"
    return c

def print_board(board):
    """
    Prints the current board with column headers A-I and row numbers 1-9,
    coloring hits (X) red and misses (o) cyan.
    """
    # Header row
    cols = '    ' + '   '.join('ABCDEFGHI')
    separator = '  +' + ('---+' * 9)
    print(cols)
    print(separator)

    # Each row with grid lines and colored cells
    for i in range(0, 9):
        row = board[i]
        colored_cells = [color_cell(cell) for cell in row]
        row_str = ' | '.join(colored_cells)
        print(f"{i+1} | {row_str} |")
        print(separator)

def handle_game(conn):
    """
    Manages the game protocol with the server: performs handshake, processes each shot and
    manages server responses to maintain correct game state. 
    """
    # Start game protocol handshake
    conn.sendall("START GAME\n".encode(FORMAT))

    positioning_ships = read_message(conn)
    if positioning_ships is None:
        print("Server disconnected before positioning ships. Exiting.")
        conn.close()
        return
    if positioning_ships != 'POSITIONING SHIPS':
        print(f"Protocol error: expected 'POSITIONING SHIPS', but received {positioning_ships!r}. Disconnecting.")
        conn.close()
        return

    ships_in_position = read_message(conn)
    if ships_in_position is None:
        print("Server disconnected before ships were positioned. Exiting.")
        conn.close()
        return
    if ships_in_position != 'SHIPS IN POSITION':
        print(f"Protocol error: expected 'SHIPS IN POSITION', but received {ships_in_position!r}. Disconnecting.")
        conn.close()
        return

    # Read server’s commit and validate it 
    commit_msg = read_message(conn)
    if commit_msg is None:
        print("Server disconnected before sending COMMIT. Exiting.")
        conn.close()
        return

    if not commit_msg.startswith("COMMIT:"):
        print(f"Protocol error: expected 'COMMIT:<hash>' but got {commit_msg!r}. Disconnecting.")
        conn.close()
        return

   # Get the session id and hashed commit message
    _, session_id, commit_hash = commit_msg.split(":", 2)

    # Check length and hex‐ness
    hex_chars = set('0123456789abcdefABCDEF')
    if len(commit_hash) != 64 or any(c not in hex_chars for c in commit_hash):
        print(f"Protocol error: commit hash is invalid ({commit_hash!r}). Disconnecting.")
        conn.close()
        return

    # Initialise board and hit counter and list for replay check
    board = create_board()
    hits = 0
    shots = 0
    transcript = [] 

    # Welcome message with game info
    print("\nWelcome to Battleship!")
    print("Enter coordinates (A1–I9) to fire. Destroy all ships in as few shots as you can.")
    print(f"{RED}X{RESET} = Hit.")
    print(f"{CYAN}o{RESET} = Miss.\n")

     # Game loop
    while True:
        print(f"Hits: {hits}/{SHIP_TOTAL}   Shots: {shots}")
        print_board(board)

        # Get user shot
        shot = input("\nEnter your shot: ").strip().upper()
        print('\n')
        print('---------------------------------------')
        print('\n')
        if not valid_shot(shot):
            print("** Invalid input. Please enter a coordinate between A1 and I9 (for example, A5). **")
            continue
        
        shots += 1
        # Send valid shot to server
        conn.sendall(f"{session_id}:{shot}\n".encode(FORMAT))

        # Read and process server response
        response = read_message(conn)
        if response is None:
            print("Server disconnected during game. Exiting.")
            conn.close()
            return

        # Verify session ID prefix
        if not response.startswith(f"{session_id}:"):
            print("Protocol error: session ID mismatch. Ending game session.")
            conn.close()
            return

        # Strip off the session ID
        payload = response.split(":", 1)[1]

        if payload == "HIT":
            hits += 1
            row, column = coords_to_index(shot)
            board[row][column] = "X"
        elif payload == "MISS":
            row, column = coords_to_index(shot)
            if board[row][column] != "X":
                board[row][column] = "o"
        else:
            print(f"Server response error: unexpected message {payload!r}. Ending game session.")
            conn.close()
            return
        
        # Record for replay check
        transcript.append((shot, payload))


        # Check for end of game
        if hits == SHIP_TOTAL:
            final_score_line = read_message(conn)
            if final_score_line is None:
                print("Server disconnected before sending final score. Exiting.")
                conn.close()
                return

            # Verify session ID on final score
            if not final_score_line.startswith(f"{session_id}:"):
                print("Protocol error: session ID mismatch on final score. Disconnecting.")
                conn.close()
                return

            final_score = final_score_line.split(":", 1)[1]
            if not final_score.isdigit():
                print(f"Protocol error: expected final score, but received {final_score!r}. Disconnecting.")
                conn.close()
                return      
            
            # Read the reveal message and verify it matches the commit
            reveal_msg = read_message(conn)               
            if reveal_msg is None:
                print("Server disconnected before sending REVEAL. Exiting.")
                conn.close()
                return

            if not reveal_msg.startswith("REVEAL:"):
                print(f"Protocol error: expected 'REVEAL:<board>' but got {reveal_msg!r}. Disconnecting.")
                conn.close()
                return

            # Get session id and revealed board
            _, reveal_session_id, revealed_board = reveal_msg.split(":", 2)

            if reveal_session_id != session_id:
                print(f"Protocol error: session ID mismatch. Disconnecting.")
                conn.close()
                return
            
            # Check hashes match
            reveal_hash = hashlib.sha256(revealed_board.encode(FORMAT)).hexdigest()
            if reveal_hash != commit_hash:
                print("ERROR: Server commitment mismatch: cheating detected!")
                conn.close()
                return
            else:
                print("Board verified: no cheating detected.")

            revealed = json.loads(revealed_board)
            for shot, reply in transcript:
                r, c = coords_to_index(shot)
                expected = "HIT" if revealed[r][c] != "." else "MISS"
                if reply != expected:
                    print(f"CHEAT DETECTED on {shot}: server said {reply} but board has {revealed[r][c]} -> expected {expected}")   
                    conn.close()
                    return
                
            print("Replay check passed: server was honest on all shots.")


            print("\nFinal Board:\n")
            print(f"Hits: {hits}/{SHIP_TOTAL}   Shots: {shots}")
            print_board(board)
            print(f"\nCongratulations! All ships destroyed. Your final score: {final_score}. Well played!")    
            conn.close()
            return


def start_client():
    """
    Parses command-line arguments, connects to the server,
    wraps the socket in TLS, and calls the game handler.
    Handles connection errors and user abort.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('host', nargs='?', default=DEFAULT_HOST)
    parser.add_argument('port', nargs='?', type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    

    try:
        # Create TLS context 
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.minimum_version = TLSVersion.TLSv1_2
        context.load_verify_locations('server.crt')

        # Create fingerprint for certificate
        with open("server.crt", "r") as f:
            expected_cert = ssl.PEM_cert_to_DER_cert(f.read())
        expected_fp = hashlib.sha256(expected_cert).hexdigest()

        # Establish TCP connection
        with socket.create_connection((args.host, args.port)) as sock:
            # Upgrade to TLS
            with context.wrap_socket(sock, server_hostname=args.host) as secure_sock:

                # Set timeout on inactive socket
                secure_sock.settimeout(60.0)
                
                # Check if the cert is valid via the finger print
                actual_cert = secure_sock.getpeercert(binary_form=True)
                actual_fp = hashlib.sha256(actual_cert).hexdigest()
                if actual_fp != expected_fp:
                    print("ERROR: server certificate fingerprint mismatch: possible MITM!")
                    return
                print("TLS handshake succeeded, starting game…")

                #Start game
                handle_game(secure_sock)

    except FileNotFoundError:
        print("Error: server.crt not found. Run startServer.sh or place the cert here.", file=sys.stderr)
        sys.exit(1)
    except (ssl.SSLError, ValueError) as e:
        print(f"TLS or certificate parsing error: {e}", file=sys.stderr)
        sys.exit(1)
    except ConnectionRefusedError:
        print(f"Connection failed: Unable to reach {args.host}:{args.port}.")
    except KeyboardInterrupt:
        print("\nGame aborted by user. Thanks for playing!")
    except BrokenPipeError:
        print("Connection lost: the server closed the connection unexpectedly.")


if __name__ == '__main__':
    start_client()