import asyncio
import json
import os
import platform
import signal
import threading
import time
import websockets
import pyotp, pytz
from datetime import datetime
import threading
import queue
import time
import gzip
import random
import signal
from functools import wraps
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from logzero import logger
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get credentials from environment variables
apikey = os.getenv('BROKER_APIKEY')
username = os.getenv('BROKER_USERNAME')
pwd = os.getenv('BROKER_PASSWORD')
token = os.getenv('BROKER_TOKEN')

# Connected clients set
connected_clients = set()

# Queue for messages from SmartAPI to WebSocket clients
message_queue = queue.Queue()

# Flag to indicate if server is shutting down
shutdown_in_progress = False

# Utility function for safe coroutine execution with error handling
async def safe_execute(coroutine, fallback=None):
    """Execute a coroutine safely, returning fallback value on exception."""
    try:
        return await coroutine
    except Exception as e:
        logger.error(f"Error in coroutine execution: {e}")
        return fallback

# Import base64 for encoding/decoding binary data
import base64

# Message compression utility
def compress_message(message_data):
    """Compress a message using gzip compression and return base64 encoded string."""
    if isinstance(message_data, dict):
        message_data = json.dumps(message_data)
    if isinstance(message_data, str):
        message_data = message_data.encode('utf-8')
    compressed = gzip.compress(message_data)
    # Encode as base64 string which is JSON serializable
    return base64.b64encode(compressed).decode('ascii')

def decompress_message(compressed_base64):
    """Decompress a base64 encoded, gzip compressed message."""
    # Convert base64 string back to bytes
    if isinstance(compressed_base64, str):
        compressed_bytes = base64.b64decode(compressed_base64)
    else:
        compressed_bytes = compressed_base64  # Handle bytes for backward compatibility
        
    decompressed = gzip.decompress(compressed_bytes)
    try:
        return json.loads(decompressed.decode('utf-8'))
    except json.JSONDecodeError:
        return decompressed.decode('utf-8')

# Heartbeat mechanism
async def heartbeat(websocket, interval=30):
    """Send periodic pings to keep the connection alive and detect disconnections."""
    try:
        while not shutdown_in_progress and websocket in connected_clients:
            await asyncio.sleep(interval)
            try:
                # Send a ping to the client
                pong_waiter = await websocket.ping()
                # Wait for the pong response with a timeout
                await asyncio.wait_for(pong_waiter, timeout=10)
                logger.debug(f"Heartbeat received from {websocket.remote_address[0]}")
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                # Connection is dead
                logger.warning(f"Heartbeat failed for {websocket.remote_address[0]}, closing connection")
                await websocket.close()
                connected_clients.discard(websocket)
                break
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")

# Graceful shutdown handler
async def graceful_shutdown(server):
    """Gracefully shutdown the server and cleanup resources."""
    global shutdown_in_progress
    shutdown_in_progress = True
    
    logger.info("Initiating graceful shutdown...")
    
    # Notify all clients about the shutdown
    if connected_clients:
        close_msg = json.dumps({
            'type': 'system',
            'message': 'Server shutting down',
            'status': 'shutdown'
        })
        
        # Send close messages to all clients
        for client in list(connected_clients):
            try:
                await client.send(close_msg)
                await client.close()
            except Exception as e:
                logger.error(f"Error notifying client about shutdown: {e}")
    
    # Close the server
    server.close()
    await server.wait_closed()
    
    # Disconnect from SmartAPI WebSocket if connected
    try:
        if sws_instance:
            # Unsubscribe from all feeds
            for exchange in token_lists.keys():
                try:
                    unsub_data = [token_lists[exchange]]
                    sws_instance.unsubscribe("ws_proxy", mode, unsub_data)
                    logger.info(f"Unsubscribed from {exchange} during shutdown")
                except Exception as e:
                    logger.error(f"Error unsubscribing from {exchange}: {e}")
    except Exception as e:
        logger.error(f"Error disconnecting from SmartAPI: {e}")
    
    logger.info("Server shutdown complete")

# Reconnecting SmartAPI WebSocket class
class ReconnectingSmartWebSocket:
    def __init__(self, auth_token, apikey, username, feed_token, max_retries=5, initial_delay=1, max_delay=30):
        self.auth_token = auth_token
        self.apikey = apikey
        self.username = username
        self.feed_token = feed_token
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.sws = None
        self.connected = False
        self.subscriptions = []  # Keep track of active subscriptions
        
        # Store original callbacks
        self.user_on_open = None
        self.user_on_data = None
        self.user_on_error = None
        self.user_on_close = None
    
    def initialize(self):
        """Initialize the SmartAPI WebSocket connection."""
        try:
            self.sws = SmartWebSocketV2(self.auth_token, self.apikey, self.username, self.feed_token, max_retry_attempt=2)
            
            # Set callbacks
            self.sws.on_open = self._on_open
            self.sws.on_data = self._on_data
            self.sws.on_error = self._on_error
            self.sws.on_close = self._on_close
            
            return self.sws
        except Exception as e:
            logger.error(f"Error initializing SmartWebSocket: {e}")
            return None
    
    def connect(self):
        """Connect to SmartAPI WebSocket with automatic reconnection."""
        retry_count = 0
        delay = self.initial_delay
        
        while retry_count < self.max_retries and not shutdown_in_progress:
            try:
                self.sws = self.initialize()
                if self.sws:
                    self.sws.connect()
                    return self.sws
            except Exception as e:
                retry_count += 1
                logger.warning(f"Connection attempt {retry_count} failed: {e}, retrying in {delay}s")
                time.sleep(delay)
                # Exponential backoff with jitter
                delay = min(self.max_delay, delay * 2 * (0.9 + 0.2 * random.random()))
        
        if retry_count >= self.max_retries:
            logger.error("Failed to connect after maximum retries")
        return None
    
    def subscribe(self, correlation_id, mode, token_list):
        """Subscribe to token list and save subscription for reconnection."""
        if self.sws:
            # Save subscription for potential reconnection
            self.subscriptions.append({
                'correlation_id': correlation_id,
                'mode': mode,
                'token_list': token_list
            })
            return self.sws.subscribe(correlation_id, mode, token_list)
        return False
    
    def unsubscribe(self, correlation_id, mode, token_list):
        """Unsubscribe from token list and remove from saved subscriptions."""
        if self.sws:
            # Remove from saved subscriptions
            self.subscriptions = [s for s in self.subscriptions 
                               if not (s['correlation_id'] == correlation_id and 
                                     s['mode'] == mode and 
                                     s['token_list'] == token_list)]
            return self.sws.unsubscribe(correlation_id, mode, token_list)
        return False
    
    def set_callbacks(self, on_open=None, on_data=None, on_error=None, on_close=None):
        """Set callbacks for the WebSocket."""
        self.user_on_open = on_open
        self.user_on_data = on_data
        self.user_on_error = on_error
        self.user_on_close = on_close
    
    def _on_open(self, wsapp):
        """On connection open callback."""
        logger.info("SmartAPI WebSocket Connected")
        self.connected = True
        
        # Resubscribe to previous subscriptions on reconnection
        for sub in self.subscriptions:
            try:
                self.sws.subscribe(sub['correlation_id'], sub['mode'], sub['token_list'])
                logger.info(f"Resubscribed after reconnection: {sub['token_list']}")
            except Exception as e:
                logger.error(f"Error resubscribing: {e}")
        
        # Call user callback if provided
        if self.user_on_open:
            self.user_on_open(wsapp)
    
    def _on_data(self, wsapp, message):
        """On message callback."""
        # Call user callback if provided
        if self.user_on_data:
            self.user_on_data(wsapp, message)
    
    def _on_error(self, wsapp, error):
        """On error callback."""
        logger.error(f"SmartAPI WebSocket Error: {error}")
        self.connected = False
        
        # Call user callback if provided
        if self.user_on_error:
            self.user_on_error(wsapp, error)
    
    def _on_close(self, wsapp):
        """On connection close callback."""
        logger.warning("SmartAPI WebSocket Closed")
        self.connected = False
        
        # Call user callback if provided
        if self.user_on_close:
            self.user_on_close(wsapp)
        
        # Attempt to reconnect unless shutdown is in progress
        if not shutdown_in_progress:
            logger.info("Attempting to reconnect...")
            threading.Thread(target=self.connect).start()

# SmartAPI Connection
def setup_smartapi():
    # Create SmartConnect object
    obj = SmartConnect(api_key=apikey)
    
    # Login API call
    data = obj.generateSession(username, pwd, pyotp.TOTP(token).now())
    refresh_token = data['data']['refreshToken']
    auth_token = data['data']['jwtToken']
    
    # Fetch the feed token
    feed_token = obj.getfeedToken()
    
    # Fetch User Profile
    res = obj.getProfile(refresh_token)
    print(res['data']['exchanges'])
    
    return auth_token, feed_token

# Setup the SmartAPI WebSocket
def setup_smartwebsocket(auth_token, feed_token):
    global token_lists, sws_instance, mode
    correlation_id = "ws_proxy"
    
    # Available token lists - exposed for clients to subscribe
    token_lists = {
        "mcx": {
            "exchangeType": 2,
            "tokens": ["57920", "57919"]
        },
        "nse": {
            "exchangeType": 1,
            "tokens": ["26000", "26009"]
        }
    }
    
    # Callback when data is received from SmartAPI
    def on_data(wsapp, message):
        try:
            # Convert timestamp from milliseconds to seconds
            timestamp = message['exchange_timestamp'] / 1000
            utc_time = datetime.fromtimestamp(timestamp, tz=pytz.UTC)  # Use timezone-aware datetime
            
            # Define the timezone for UTC +05:30
            timezone = pytz.timezone('Asia/Kolkata')
            
            # Convert UTC time to UTC +05:30
            local_time = utc_time.astimezone(timezone)
            formatted_timestamp = local_time.strftime('%Y-%m-%d %H:%M:%S')
            
            # Process the message data
            processed_data = {
                "exchange_type": message['exchange_type'],
                "token": message['token'],
                "last_traded_price": message['last_traded_price'] / 100,  # Dividing by 100 as per original code
                "timestamp": formatted_timestamp
            }
            
            # Log the data
            logger.info(f"Exchange Type: {processed_data['exchange_type']}, Token: {processed_data['token']}, "
                       f"Last Traded Price: {processed_data['last_traded_price']:.2f}, Timestamp: {processed_data['timestamp']}")
            
            # Put the message in the queue for the async task to handle
            if connected_clients:
                # Compress the message before queuing it
                compressed_data = {
                    'type': 'market_data',
                    'compressed': True,
                    'data': compress_message(processed_data)
                }
                message_queue.put(json.dumps(compressed_data))
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    # WebSocket callbacks
    def on_open(wsapp):
        logger.info("SmartAPI WebSocket Connected")
        # No longer auto-subscribing, will be controlled by client
    
    def on_error(wsapp, error):
        logger.error(f"SmartAPI WebSocket Error: {error}")
    
    def on_close(wsapp):
        logger.info("SmartAPI WebSocket Connection Closed")
    
    # Create reconnecting SmartWebSocketV2 instance
    reconnecting_sws = ReconnectingSmartWebSocket(auth_token, apikey, username, feed_token, max_retries=10)
    
    # Set callbacks
    reconnecting_sws.set_callbacks(on_open=on_open, on_data=on_data, on_error=on_error, on_close=on_close)
    
    return reconnecting_sws

# Broadcast message to all connected clients
async def broadcast_message(message):
    if not connected_clients:  # No clients connected
        return
    
    try:
        # Check if it's a compressed message
        message_data = json.loads(message)
        
        if message_data.get('type') == 'market_data' and message_data.get('compressed'):
            # Get the compressed data
            compressed_data = message_data['data']
            
            # For clients that don't support compression, decompress the data
            # This allows for backward compatibility
            original_data = decompress_message(message_data['data'])
            uncompressed_message = json.dumps(original_data)
        else:
            # Not compressed, use as is
            uncompressed_message = message
        
        # Create a copy of the set as it might change during iteration
        clients_copy = connected_clients.copy()
        for client in clients_copy:
            try:
                # Send the uncompressed message to all clients
                # In a production environment, you might want to track which clients support compression
                await safe_execute(client.send(uncompressed_message))
            except websockets.exceptions.ConnectionClosed:
                # Client might have disconnected during the broadcast
                connected_clients.discard(client)
                logger.info(f"Client disconnected during broadcast. Current clients: {len(connected_clients)}")
            except Exception as e:
                logger.error(f"Error sending message to client: {e}")
                connected_clients.discard(client)
    except Exception as e:
        logger.error(f"Error processing message for broadcast: {e}")
        # Fall back to sending the raw message
        clients_copy = connected_clients.copy()
        for client in clients_copy:
            try:
                await client.send(message)
            except Exception:
                connected_clients.discard(client)

# Process messages from the queue and broadcast them
async def process_message_queue():
    while True:
        try:
            # Check if there are messages in the queue
            if not message_queue.empty():
                message = message_queue.get(block=False)
                await broadcast_message(message)
            else:
                # If no messages, wait a bit
                await asyncio.sleep(0.01)
        except queue.Empty:
            # Queue is empty, continue
            await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Error in message queue processing: {e}")
            await asyncio.sleep(0.1)

# Global SmartAPI WebSocket instance
sws_instance = None
token_lists = {}
mode = 1  # mode = 1, Fetches LTP quotes

# Process commands from clients to subscribe/unsubscribe
async def process_client_command(websocket, command_data):
    try:
        command = command_data.get('command')
        exchange = command_data.get('exchange')
        correlation_id = "ws_proxy"
        
        if not command or not exchange:
            await websocket.send(json.dumps({
                'status': 'error',
                'message': 'Missing command or exchange parameters'
            }))
            return
            
        if exchange not in token_lists:
            await websocket.send(json.dumps({
                'status': 'error',
                'message': f'Unknown exchange: {exchange}'
            }))
            return
            
        if command == 'subscribe':
            # Subscribe to the specified exchange
            sub_data = [token_lists[exchange]]
            sws_instance.subscribe("ws_proxy", mode, sub_data)
            logger.info(f"Subscribed to {exchange}: {sub_data}")
            await websocket.send(json.dumps({
                'status': 'success',
                'message': f'Subscribed to {exchange}',
                'data': sub_data
            }))
            
        elif command == 'unsubscribe':
            # Unsubscribe from the specified exchange
            unsub_data = [token_lists[exchange]]
            sws_instance.unsubscribe("ws_proxy", mode, unsub_data)
            logger.info(f"Unsubscribed from {exchange}: {unsub_data}")
            await websocket.send(json.dumps({
                'status': 'success',
                'message': f'Unsubscribed from {exchange}',
                'data': unsub_data
            }))
            
        elif command == 'list_exchanges':
            # Return available exchanges
            await websocket.send(json.dumps({
                'status': 'success',
                'message': 'Available exchanges',
                'data': list(token_lists.keys())
            }))
            
        else:
            await websocket.send(json.dumps({
                'status': 'error',
                'message': f'Unknown command: {command}'
            }))
            
    except Exception as e:
        logger.error(f"Error processing client command: {e}")
        await websocket.send(json.dumps({
            'status': 'error',
            'message': f'Error processing command: {str(e)}'
        }))

# WebSocket server handler
async def websocket_handler(websocket):
    # Register the client
    connected_clients.add(websocket)
    client_ip = websocket.remote_address[0]
    logger.info(f"New client connected from {client_ip}. Total clients: {len(connected_clients)}")
    
    # Start heartbeat for this client
    heartbeat_task = asyncio.create_task(heartbeat(websocket))
    
    try:
        # Send available exchanges to the client
        await safe_execute(websocket.send(json.dumps({
            'type': 'info',
            'message': 'Connected to WebSocket proxy server',
            'available_exchanges': list(token_lists.keys())
        })))
        
        # Process messages from the client
        async for message in websocket:
            try:
                data = json.loads(message)
                if 'command' in data:
                    # Process client commands
                    await process_client_command(websocket, data)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from client: {message}")
                await safe_execute(websocket.send(json.dumps({
                    'status': 'error',
                    'message': 'Invalid JSON format'
                })))
            except Exception as e:
                logger.error(f"Error processing message from client: {e}")
                await safe_execute(websocket.send(json.dumps({
                    'status': 'error',
                    'message': f'Error: {str(e)}'
                })))
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Connection closed by client {client_ip}")
    except Exception as e:
        logger.error(f"Unexpected error in websocket handler: {e}")
    finally:
        # Cancel the heartbeat task
        if heartbeat_task and not heartbeat_task.done():
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Unregister the client when disconnected
        connected_clients.discard(websocket)
        
        # If no clients are connected, unsubscribe from all exchanges to save resources
        if len(connected_clients) == 0 and sws_instance:
            correlation_id = "ws_proxy"
            for exchange in token_lists.keys():
                try:
                    # Create unsubscribe data for this exchange
                    unsub_data = [token_lists[exchange]]
                    sws_instance.unsubscribe("ws_proxy", mode, unsub_data)
                    logger.info(f"Unsubscribed from {exchange} after client disconnect")
                except Exception as e:
                    logger.error(f"Error unsubscribing from {exchange}: {e}")
                    
        logger.info(f"Client {client_ip} disconnected. Remaining clients: {len(connected_clients)}")

# Main function
async def main():
    global sws_instance
    
    # Load environment variables if not already loaded
    load_dotenv()
    
    # Setup SmartAPI
    auth_token, feed_token = setup_smartapi()
    
    # Setup SmartAPI WebSocket with reconnection capabilities
    sws_instance = setup_smartwebsocket(auth_token, feed_token)
    
    # Start SmartAPI WebSocket connection in a separate thread
    smartapi_thread = threading.Thread(target=sws_instance.connect)
    smartapi_thread.daemon = True  # Set as daemon so it exits when main thread exits
    smartapi_thread.start()
    
    # Setup WebSocket server
    host = "0.0.0.0"  # Listen on all interfaces
    port = 8765  # WebSocket port
    
    # Start the WebSocket server
    server = await websockets.serve(lambda ws: websocket_handler(ws), host, port)
    logger.info(f"WebSocket proxy server started at ws://{host}:{port}")
    
    # Start message queue processing task
    message_processor = asyncio.create_task(process_message_queue())
    
    # Add signal handling for graceful shutdown
    loop = asyncio.get_running_loop()
    
    # Get the current platform
    current_platform = platform.system()
    
    if current_platform == "Windows":
        # Windows-specific approach using a separate thread to handle Ctrl+C
        
        # Create an event to signal when we should shutdown
        shutdown_event = threading.Event()
        
        def shutdown_handler():
            """Handler to monitor for shutdown in a separate thread"""
            try:
                # This will block until KeyboardInterrupt (Ctrl+C)
                while not shutdown_event.is_set():
                    time.sleep(0.1)
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received, initiating graceful shutdown")
                # Use call_soon_threadsafe to schedule the shutdown from a different thread
                loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(graceful_shutdown(server))
                )
        
        # Start the handler in a separate thread
        shutdown_thread = threading.Thread(target=shutdown_handler, daemon=True)
        shutdown_thread.start()
        logger.info("Windows shutdown handler initialized")
    else:
        # UNIX-style signal handlers for SIGINT and SIGTERM
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    sig, 
                    lambda: asyncio.create_task(graceful_shutdown(server))
                )
                logger.info(f"Added signal handler for {sig.name}")
            except NotImplementedError:
                logger.warning(f"Signal {sig.name} not supported on this platform")
    
    # Keep the server running until signal received or closed
    await server.wait_closed()

# Run the main function
if __name__ == "__main__":
    try:
        # Import signal at the top of the file if not already imported
        import signal
        
        # Run the main function
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopping due to keyboard interrupt")
        # Note: The actual shutdown logic is handled by the signal handlers
    except asyncio.CancelledError:
        logger.info("Tasks have been cancelled during shutdown")
    except Exception as e:
        logger.error(f"Error in main function: {e}")
    finally:
        # Ensure shutdown is completed and logged
        logger.info("WebSocket proxy server has shut down")
