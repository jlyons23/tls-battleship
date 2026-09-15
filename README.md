# TLS Battleship: A Protocol With an Untrusted Server

A client-server Battleship game in Python. The game is mostly a vehicle for the security
model, where the client treats the server as untrusted and checks cryptographically that
it played fair.

In ordinary client-server Battleship the server holds the board and reports HIT or MISS.
Nothing stops it moving ships out of the way, or lying about a shot.

The wire format is documented in [`PROTOCOL.md`](PROTOCOL.md).

## The protocol

**Transport.** TLS 1.2 or higher, with the client pinning the server certificate by
SHA-256 fingerprint. A certificate that is valid but not the expected one is rejected, so
a man-in-the-middle holding a different cert cannot complete the handshake.

**Commitment.** Before play begins the server serialises the board, hashes it with
SHA-256 and sends the digest as a `COMMIT` message. This binds the server to one board
without revealing it. The client validates the digest is well-formed before accepting it.

**Play.** Every message in both directions is prefixed with a per-session UUID. Messages
carrying the wrong session ID are rejected, which prevents a reply from one session being
replayed into another. The client records a transcript of every shot and the response it
received.

**Reveal and verification.** When the game ends the server sends the board in the clear.
The client then runs two checks:

1. Hash the revealed board and compare it to the original commitment. A mismatch means
   the server played a different board than the one it committed to.
2. Replay the full shot transcript against the revealed board. Every HIT and MISS is
   recomputed and compared to what the server actually said at the time.

The first check catches a server that swapped the board. The second catches a server that
kept its board but lied about individual shots, which a commitment alone would not detect.

## Other defences

- Line-oriented reads with a maximum message length, so an unterminated stream cannot
  exhaust memory.
- Socket timeouts on both ends to drop stalled connections.
- Server-side rate limiting on incoming shots.
- Strict format validation on every protocol message. Malformed input drops the
  connection.

## Running it

Requires Python 3.6+ and the `cryptography` package.

```
pip install cryptography
```

On Linux or macOS:

```
./startServer.sh          # generates a self-signed cert on first run, then listens
./startClient.sh          # in a second terminal
```

On Windows:

```
startServer.bat
startClient.bat
```

The server defaults to port 12345, the client to `127.0.0.1:12345`. Both accept
overrides, for example `./startServer.sh 23456` and `./startClient.sh 192.168.0.5 23456`,
or the same arguments to the `.bat` equivalents.

The launcher scripts only generate the certificate if needed and pass arguments through,
so the Python files can also be run directly on any platform:

```
python generate_cert.py
python secure_server.py
python secure_client.py
```

The client needs `server.crt` present to pin against, so it runs on the same machine as
the server, or the certificate is copied across first.

## Structure

```
tls-battleship/
├── PROTOCOL.md        # wire format and message sequence
├── secure_server.py   # board generation, commitment, game loop, reveal
├── secure_client.py   # TLS setup, cert pinning, gameplay, verification
├── generate_cert.py   # self-signed certificate and key generation
├── startServer.sh     
├── startClient.sh
├── startServer.bat    
└── startClient.bat
```

## Notes and limitations

- The certificate is self-signed and pinned by fingerprint rather than validated against
  a CA. That means the client needs the expected certificate in advance, so it doesn't
  scale past a known pair of endpoints.
- The server is single-threaded and handles one client at a time.
- The commitment proves the server did not change the board mid-game. It does not
  constrain which board the server chose in the first place, so a server could still
  commit to a deliberately awkward layout.
- Rate limiting drops the connection rather than throttling.
