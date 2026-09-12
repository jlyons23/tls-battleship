#!/usr/bin/env python3
import socket
import argparse
import random
import ssl
from ssl import TLSVersion
import time
import json
import hashlib
import uuid

# Set constants
HOST = '127.0.0.1'
DEFAULT_PORT = 12345
FORMAT = 'utf-8'


# Dictonary mapping ship symbols to their lengths
# C - Canberra-class Landing Helicopter Dock
# H - Hobart-class Destroyer
# L - Leeuwin-class Survey Vessel
# A - Armidale-class Patrol Boat
SHIPS = {
    'C': 5,  
    'H': 4, 
    'L': 3, 
    'A': 2, 
}


def place_ship(board, symbol, length):
    """
    Attemps to randomly place a ship of given symbol and length on the board.
    Keeps trying until a valid position is found.
    """
    while True:
        orientation = random.choice(['H','V'])
        #Check horizontal cells
        if orientation == "H": 
            row = random.randrange(9)
            column = random.randrange(9 - length + 1)
            if all(board[row][column+i] == '.' for i in range(length)):
                for i in range(length):
                    board[row][column+i] = symbol
                return
        #Check vertical cells
        else:
            row = random.randrange(9 - length + 1)
            column = random.randrange(9)
            if all(board[row+i][column] == '.' for i in range(length)):
                for i in range(length):
                    board[row+i][column] = symbol
                return
    

def create_board():
    """
    Returns a 9x9 board with each ship placed.
    """
    board = [["." for _ in range(9)] for _ in range(9)]

    for symbol, length in SHIPS.items():
        place_ship(board, symbol, length)
    
    return board

def read_message(conn):
    """
    Reads data in one byte increments until a newline character is found.
    Returns the string decoded and stripped.
    Returns an None when connection drops.
    """
    data = b''
    max_len = 512
    while not data.endswith(b'\n'):
        if len(data) >= max_len:
            # Too many bytes without a newline -> protocol error
            print("Protocol error: incoming line too long. Disconnecting.")
            return None
        try:
            char = conn.recv(1)
        except ConnectionResetError:
            return None
        except socket.timeout:
            print("Connection timed out. Closing.")
            return None
        if not char:
            return None
        data += char
    return data.decode(FORMAT).rstrip('\r\n')

def valid_shot(coords):
    """
    Validates the shot coordinates.
    """
    return len(coords) == 2 and coords[0] in 'ABCDEFGHI' and coords[1] in '123456789'

def coords_to_index(coords):
    """
    Converts shot coordinates from letter number to row column
    """
    column = ord(coords[0]) - ord('A')
    row = int(coords[1]) - 1
    return (row, column)

def handle_client(conn, addr):
    """
    Manages a single client session: performs handshake, processes each shot,
    and sends HIT/MISS and final score messages to the client.
    """
    # Create nonce for session
    session_id = uuid.uuid4().hex
    print(f"Starting session {session_id} for {addr!r}")

    # Check initial handshake message
    start_message = read_message(conn)
    if start_message is None:
        print("Client disconnected before starting game.")
        conn.close()
        return
    if start_message != 'START GAME':
        print(f"Protocol error: expected 'START GAME' but received: {start_message!r}. Disconnecting.")
        conn.close()
        return
    print("Client: START GAME")

    # Send POSITIONING SHIPS handshake response
    conn.sendall('POSITIONING SHIPS\n'.encode(FORMAT))
    print("Server: POSITIONING SHIPS")
    
    # Initialise game board and counters
    board = create_board()
    hits_required = sum(SHIPS.values())
    hits = 0
    score = 0

    # Inform client that the game is ready to be played
    conn.sendall('SHIPS IN POSITION\n'.encode(FORMAT))
    print("Server: SHIPS IN POSITION")

    # Create a hash of the original board to be used for a commit reveal
    serialized_board = json.dumps(board)
    hashed_board = hashlib.sha256(serialized_board.encode(FORMAT)).hexdigest()
    conn.sendall(f"COMMIT:{session_id}:{hashed_board}\n".encode(FORMAT))
    print(f"Server: commit message sent for {session_id}")

    # Prepare message send rate trackers
    last_shot_time    = 0.0
    min_interval_secs = 0.2

    # Loop until all ships are sunk
    while hits < hits_required:
        now = time.time()
        if now - last_shot_time < min_interval_secs:                   
            print("Server: Rate limit exceeded, disconnecting.")
            conn.close()
            return
        last_shot_time = now

        shot = read_message(conn)
        if shot is None:
            print("Client disconnected during game.")
            conn.close()
            return
        # Verify session ID prefix
        if not shot.startswith(f"{session_id}:"):
            print(f"Protocol error: session ID mismatch on shot: {shot!r}. Disconnecting.")
            conn.close()
            return

        # Strip off the session ID
        shot = shot.split(":", 1)[1]

        if not valid_shot(shot):
            print(f"Protocol error: expected valid shot but received: {shot!r}. Disconnecting.")
            conn.close()
            return

        score += 1
        print(f"Client: {shot}")

        row, column = coords_to_index(shot)
        cell = board[row][column]

        # Send HIT or MISS message to client
        if cell in SHIPS:
            hits += 1
            board[row][column] = 'X'
            conn.sendall(f"{session_id}:HIT\n".encode(FORMAT))
            print("Server: HIT")
        else:
            conn.sendall(f"{session_id}:MISS\n".encode(FORMAT))
            print("Server: MISS")

    # Send final score and close connection
    conn.sendall(f"{session_id}:{score}\n".encode(FORMAT))
    print(f"Server: {score}")

    # Send the revealed board to the client for confirmation
    conn.sendall(f"REVEAL:{session_id}:{serialized_board}\n".encode(FORMAT))
    print(f"Server: Revealed board sent for session id: {session_id}")
    conn.close()


def start_server():
    """
    Parses arguments, binds to the specified port, and accepts incoming connections.
    Handles errors and keyboard interrupt.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('port', nargs='?', type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    # Create TLS context
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = TLSVersion.TLSv1_2  
    context.load_cert_chain("server.crt", "server.key")

     # Create IPv4/TCP socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((HOST, args.port))
        server.listen()
        print(f"Secure server listening on port {args.port}...")
        
        try:
            while True:
                raw_conn, addr = server.accept()
                try:
                    # Upgrade to TLS
                    with context.wrap_socket(raw_conn, server_side=True) as conn:
                        # Set timeout on inactive socket
                        conn.settimeout(60.0)
                        handle_client(conn, addr)
                except ssl.SSLError as e:
                    print(f"SSL error with {addr}: {e}")
        except KeyboardInterrupt:
            print("\nServer shutting down.")
            
    print(f"Server has stopped listening on port {args.port}.")

if __name__ == '__main__':
    start_server()
