# package import statement
from SmartApi import SmartConnect #or from smartapi.smartConnect import SmartConnect

import os
import pyotp, time, pytz
from datetime import datetime
import threading
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get credentials from environment variables
apikey = os.getenv('APIKEY')
username = os.getenv('USERNAME')
pwd = os.getenv('PASSWORD')
token = os.getenv('TOKEN')

#create object of call
obj=SmartConnect(api_key=apikey)

#login api call

data = obj.generateSession(username,pwd,pyotp.TOTP(token).now())
#cls
# print (data)
refreshToken= data['data']['refreshToken']
AUTH_TOKEN = data['data']['jwtToken']

#fetch the feedtoken
FEED_TOKEN =obj.getfeedToken()
#print ("Feed Token: "+FEED_TOKEN)

#fetch User Profile
res= obj.getProfile(refreshToken) 
print(res['data']['exchanges'])


from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from logzero import logger


correlation_id = "ws_test"
action = 1 #action = 1, subscribe to the feeds action = 2 - unsubscribe
mode = 2   #mode = 2 , Fetches quotes

token_list = [
    {
        "exchangeType": 2,
        "tokens": ["57920","57919"]
    }
]


sws = SmartWebSocketV2(AUTH_TOKEN, apikey, username, FEED_TOKEN,max_retry_attempt=5)

def on_data(wsapp, message):
    try:
        # Assuming 'message' is a dictionary, not a list
        item = message

        # Converting and formatting the timestamp
        timestamp = datetime.fromtimestamp(item['exchange_timestamp'] / 1000, pytz.timezone('Asia/Kolkata'))

        # Formatting the data
        formatted_item = {
            'Exchange Type': item['exchange_type'],
            'Token': item['token'],
            'Timestamp (IST)': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'Open Price': f"{item['open_price_of_the_day'] / 100:.2f}",
            'High Price': f"{item['high_price_of_the_day'] / 100:.2f}",
            'Low Price': f"{item['low_price_of_the_day'] / 100:.2f}",
            'Close Price': f"{item['closed_price'] / 100:.2f}",
            'Last Traded Price': f"{item['last_traded_price'] / 100:.2f}",
        }

        # Logging the formatted data
        logger.info(formatted_item)
    except Exception as e:
        logger.error(f"Error processing message: {e}")



def on_open(wsapp):
    logger.info("on open")
    sws.subscribe(correlation_id, mode, token_list)
    
    
    # sws.unsubscribe(correlation_id, mode, token_list1)


def on_error(wsapp, error):
    logger.info(error)


def on_close(wsapp):
    logger.info("Close")



def close_connection():
    sws.close_connection()


# Assign the callbacks.
sws.on_open = on_open
sws.on_data = on_data
sws.on_error = on_error
sws.on_close = on_close

threading.Thread(target=sws.connect).start()