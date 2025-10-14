# app.py
import os
import uuid
from io import BytesIO
from dotenv import load_dotenv
from flask import Flask, request, send_file
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from google import genai
from google.genai import types
from PIL import Image
import logging

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize clients
twilio_client = Client()
gemini_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

# Store generated images temporarily (in production, use a proper storage solution)
generated_images = {}

@app.route('/whatsapp', methods=['POST'])
def incoming_whatsapp():
    """Handles incoming WhatsApp messages."""
    incoming_msg = request.form.get('Body', '').strip()
    from_number = request.form.get('From')

    logger.info(f"Received message from {from_number}: {incoming_msg}")

    # Ignore empty messages
    if not incoming_msg:
        return str(MessagingResponse())

    try:
        # Generate image using Nano Banana API
        logger.info(f"Generating image for prompt: {incoming_msg}")
        
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[incoming_msg],
        )

        image_data = None
        response_text = ""

        # Process the response parts
        for part in response.candidates[0].content.parts:
            if part.text is not None:
                response_text += part.text + "\n"
            elif part.inline_data is not None:
                image_data = part.inline_data.data

        if image_data:
            # Generate unique filename
            image_filename = f"generated_{uuid.uuid4().hex[:8]}.png"
            
            # Save image locally
            image = Image.open(BytesIO(image_data))
            image.save(image_filename)
            logger.info(f"Image saved as: {image_filename}")
            
            # Store reference (optional cleanup later)
            generated_images[image_filename] = True
            
            # Get the public URL for the image
            ngrok_url = os.getenv('NGROK_URL', 'https://4e8be9ba5910.ngrok-free.app')
            image_url = f"{ngrok_url}/images/{image_filename}"
            
            # Send the image via Twilio
            message = twilio_client.messages.create(
                body=f"🎨 Here's your generated image for: '{incoming_msg}'",
                from_='whatsapp:+14155238886',  # Your Twilio Sandbox number
                to=from_number,
                media_url=[image_url]
            )
            
            logger.info(f"Image sent via Twilio, SID: {message.sid}")
            
            # Immediate response to WhatsApp
            twiml_response = MessagingResponse()
            twiml_response.message("✅ Your image has been generated and is on its way!")
            return str(twiml_response)
            
        else:
            # If no image was generated
            twiml_response = MessagingResponse()
            if response_text:
                twiml_response.message(f"⚠️ No image generated, but here's the response:\n{response_text}")
            else:
                twiml_response.message("❌ Sorry, I couldn't generate an image from that prompt. Please try something else!")
            return str(twiml_response)

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        twiml_response = MessagingResponse()
        twiml_response.message("❌ Sorry, an error occurred while processing your request. Please try again.")
        return str(twiml_response)

@app.route('/images/<filename>')
def serve_image(filename):
    """Serve generated images"""
    try:
        logger.info(f"Serving image: {filename}")
        return send_file(filename, mimetype='image/png')
    except FileNotFoundError:
        logger.error(f"Image not found: {filename}")
        return "Image not found", 404

@app.route('/health')
def health_check():
    return "🚀 WhatsApp Image Bot is running with Nano Banana API!"

# Cleanup function (optional - for production you might want proper file management)
import atexit
import glob

def cleanup_generated_images():
    """Clean up generated images on shutdown"""
    try:
        for filename in glob.glob("generated_*.png"):
            os.remove(filename)
            logger.info(f"Cleaned up: {filename}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

atexit.register(cleanup_generated_images)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)