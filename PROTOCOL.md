# Protocol Specification

All commands and responses are ASCII text terminated by a single line-feed character
(LF, ASCII 10). Messages are case-sensitive. Any unexpected or out-of-order message
causes the receiver to drop the connection. Connections are also dropped when a line is
longer than 512 bytes, if idle for more than 60 seconds, or if shots are sent at a
frequency faster than one every 0.2 seconds.

Before any exchanges, the client opens a TCP socket to the server's host and port and
immediately performs a TLS 1.2+ handshake. Only once the TLS channel is established can
the messages below occur.

## Message sequence

1. Client sends `START GAME` to request a new game session.
2. Server replies `POSITIONING SHIPS` to acknowledge and begins placing ships.
3. Server sends `SHIPS IN POSITION` once the 9x9 board is set up.
4. Server sends `COMMIT:<session id>:<hash>`, where `<session id>` is a 32-hex-digit
   session UUID and `<hash>` is the 64-hex-digit SHA-256 hash of the JSON-serialised
   board.

   From this point on, every message must be prefixed with `<session id>`.

5. The main game loop repeats until all ships are sunk:
   - Client sends `<session id>:<cell>` (for example `abc123...:E5`) indicating where to
     fire.
   - Server replies `<session id>:HIT` or `<session id>:MISS`. Duplicate shots always
     return `MISS`.
6. Once the client has accumulated the required number of hits (14), the server sends
   `<session id>:<score>`, with `<score>` as an integer.
7. Immediately after the score, the server sends `REVEAL:<session id>:<JSON_board>`,
   where `<JSON_board>` is the exact output of `json.dumps(board)`: a JSON array of nine
   arrays, each of length nine, where each element is either `"."` or the single
   character ship symbol.
8. Server closes the TLS connection.

## Example exchange

```
Client: START GAME
Server: POSITIONING SHIPS
Server: SHIPS IN POSITION
Server: COMMIT:<session id>:<hash>
Client: <session id>:E5
Server: <session id>:MISS
Client: <session id>:B3
Server: <session id>:HIT
... (12 more shots) ...
Client: <session id>:H7
Server: <session id>:HIT
Server: <session id>:<score>
Server: REVEAL:<session id>:<JSON_board>
```
