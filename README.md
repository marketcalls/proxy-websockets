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

## WebSocket URL and Testing

By default, the WebSocket proxy server runs on port 8765 and binds to all interfaces, making it accessible from any device on your network.

### Connection URL

- **Local usage**: `ws://localhost:8765`
- **LAN usage**: `ws://your-local-ip:8765` (e.g., `ws://192.168.1.100:8765`)

### Testing the WebSocket Server

You can test the WebSocket server in several ways:

1. **Using the included HTML client**:
   - Open `client.html` in a web browser
   - The client will automatically connect to the WebSocket server at `ws://localhost:8765`
   - You will see real-time market data display once connected

2. **Using WebSocket testing tools**:
   - [Websocat](https://github.com/vi/websocat) (command-line tool): 
     ```
     websocat ws://localhost:8765
     ```
   - [Postman](https://www.postman.com/) (GUI tool):
     - Create a new WebSocket request to `ws://localhost:8765`
     - Send a subscription message: `{"command": "subscribe", "exchange": "nse"}`

3. **Using browser developer tools**:
   - Open your browser's developer console (F12)
   - Execute the following JavaScript:
     ```javascript
     const ws = new WebSocket('ws://localhost:8765');
     ws.onopen = () => {
       console.log('Connected');
       ws.send(JSON.stringify({command: 'subscribe', exchange: 'nse'}));
     };
     ws.onmessage = (event) => console.log(JSON.parse(event.data));
     ```

## Client Example

A simple HTML client is included in the repository (`client.html`). Open it in a web browser to view the real-time market data stream.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
