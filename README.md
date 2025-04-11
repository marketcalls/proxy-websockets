# SmartAPI WebSocket Proxy

A reliable and efficient WebSocket proxy for market data from SmartAPI broker. This proxy server handles authentication, connection management, and provides real-time market data to multiple client applications.

## Features

- **Automatic Reconnection**: Robust reconnection with exponential backoff if the connection to SmartAPI is lost
- **Heartbeat Mechanism**: Periodic pings to keep connections alive and detect disconnections
- **Message Compression**: Gzip compression with Base64 encoding to reduce bandwidth usage
- **Graceful Shutdown**: Proper cleanup of resources when the server is shutting down
- **Error Handling**: Improved error handling to prevent server crashes
- **Multiple Client Support**: Support for multiple client connections to the same data stream
- **Secure Credential Storage**: Stores API keys and credentials in .env files

## Setup

1. Clone this repository
2. Create a `.env` file based on `.env.example` with your SmartAPI credentials
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run the WebSocket proxy:
   ```
   python websocket_proxy.py
   ```

## Usage

The WebSocket proxy server provides a simple interface for clients to connect and receive market data:

1. Connect to the WebSocket server at `ws://localhost:8765`
2. Subscribe to market data by sending a JSON command:
   ```json
   {
     "command": "subscribe",
     "exchange": "nse" 
   }
   ```
3. Receive real-time market data

## Client Example

A simple HTML client is included in the repository (`client.html`). Open it in a web browser to view the real-time market data stream.

## License

MIT License

Copyright (c) 2025 Marketcalls

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
