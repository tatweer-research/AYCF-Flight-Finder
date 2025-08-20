import random
import numpy as np
import cv2
import base64
from io import BytesIO
import streamlit as st

def generate_captcha():
    """
    Generate a simple two-digit captcha image.
    Returns the image as a base64 encoded string and the correct answer.
    """
    # Generate random two-digit number
    captcha_number = random.randint(10, 99)
    
    # Create blank image
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img.fill(255)  # White background
    
    # Add some noise to the background
    for _ in range(100):
        x = random.randint(0, img.shape[1]-1)
        y = random.randint(0, img.shape[0]-1)
        color = (random.randint(0, 200), random.randint(0, 200), random.randint(0, 200))
        cv2.circle(img, (x, y), random.randint(1, 3), color, -1)
    
    # Add some random lines
    for _ in range(5):
        pt1 = (random.randint(0, img.shape[1]-1), random.randint(0, img.shape[0]-1))
        pt2 = (random.randint(0, img.shape[1]-1), random.randint(0, img.shape[0]-1))
        color = (random.randint(0, 200), random.randint(0, 200), random.randint(0, 200))
        cv2.line(img, pt1, pt2, color, random.randint(1, 2))
    
    # Add the number
    text = str(captcha_number)
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(text, font, 1.5, 2)[0]
    
    # Position the text in the center
    x = (img.shape[1] - text_size[0]) // 2
    y = (img.shape[0] + text_size[1]) // 2
    
    # Add some random rotation/distortion to the text
    angle = random.uniform(-10, 10)
    center = (x + text_size[0]//2, y - text_size[1]//2)
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    
    # Apply a slight distortion to the original image before adding text
    distorted = cv2.warpAffine(img, rotation_matrix, (img.shape[1], img.shape[0]))
    
    # Add text with a random color
    color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 100))
    cv2.putText(distorted, text, (x, y), font, 1.5, color, 2)
    
    # Convert the image to base64 for displaying in Streamlit
    _, buffer = cv2.imencode('.png', distorted)
    img_str = base64.b64encode(buffer).decode('utf-8')
    
    return img_str, captcha_number

class CaptchaError(Exception):
    pass

class CaptchaNotSetError(CaptchaError):
    pass

class CaptchaIncorrectError(CaptchaError):
    pass

def display_captcha():
    """
    Display the captcha in Streamlit.
    Does not perform validation - this is expected to be done with validate_captcha().
    """
    # Initialize or refresh captcha if not already in session state
    if 'captcha_answer' not in st.session_state or st.session_state.get('refresh_captcha', False):
        img_str, answer = generate_captcha()
        st.session_state.captcha_img = img_str
        st.session_state.captcha_answer = answer
        st.session_state.refresh_captcha = False
    
    # Display the captcha image
    st.markdown("Please enter the number shown in the image below:")
    st.markdown(f'<img src="data:image/png;base64,{st.session_state.captcha_img}" alt="captcha">', unsafe_allow_html=True)
    
    # Get user input
    st.text_input("Captcha:", key="captcha_input")

def validate_captcha():
    """
    Validate the captcha input against the stored answer.
    Raises CaptchaError if validation fails.
    """
    user_input = st.session_state.get("captcha_input", "")
    user_input = str(user_input).strip()
    
    if not user_input:
        raise CaptchaNotSetError("Please enter the captcha code.")
    
    try:
        if int(user_input) != st.session_state.captcha_answer:
            raise CaptchaIncorrectError("Incorrect captcha. Please try again.")
    except ValueError:
        raise CaptchaIncorrectError("Please enter a valid number.")
    
    # If we get here, captcha is valid
    return True
