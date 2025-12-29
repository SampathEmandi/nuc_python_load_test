"""
Encryption utilities for WebSocket communication matching the JavaScript implementation.

This module provides encryption and decryption functions that are compatible
with the client-side JavaScript encryption scheme using CryptoJS.
"""
import base64
import secrets
import string
from typing import Optional

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    _USE_PYCRYPTODOME = True
except ImportError:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.backends import default_backend
        _USE_PYCRYPTODOME = False
    except ImportError:
        raise ImportError(
            "Either pycryptodome or cryptography library is required. "
            "Install with: pip install pycryptodome or pip install cryptography"
        )


# Constants matching JavaScript implementation
SEPARATOR = "rE7pRxTGlqT6"
DYNAMIC_PADDING_LENGTH = 12
KEY_LENGTH = 32
IV_LENGTH = 16

# Morph rules matching JavaScript
MORPH_RULES = {
    "R": "Ef4YsO2cbQZ2",
    "W": "U4Bai5Qn1ZCp",
    "q": "zR2H8Cd5maEc",
    "a": "yUz4P1a7Dz6v",
    "E": "Xm5VaT2B7c9a",
}


def _get_random_alphanumeric_string(length: int) -> str:
    """Generate a random alphanumeric string of specified length."""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def _morph_string(input_string: str) -> str:
    """
    Morph a string by replacing characters according to MORPH_RULES.
    
    Args:
        input_string: The string to morph
        
    Returns:
        The morphed string
    """
    output = ""
    for char in input_string:
        output += MORPH_RULES.get(char, char)
    return output


def _demorph_string(input_string: str) -> str:
    """
    Reverse the morphing process by replacing morphed substrings back to original characters.
    
    Args:
        input_string: The morphed string to demorph
        
    Returns:
        The demorphed string
    """
    # Create reverse mapping from morphed values to original keys
    demorph_map = {value: key for key, value in MORPH_RULES.items()}
    
    output = ""
    i = 0
    while i < len(input_string):
        match_found = False
        # Check each morphed value to see if it matches at current position
        for morphed_value, original_char in demorph_map.items():
            if input_string[i:i+len(morphed_value)] == morphed_value:
                output += original_char
                i += len(morphed_value)
                match_found = True
                break
        if not match_found:
            output += input_string[i]
            i += 1
    return output


def encrypt(input_string: str, encryption_enabled: bool = True) -> str:
    """
    Encrypt a string using AES CBC mode with morphing.
    
    This function matches the JavaScript encryption implementation exactly.
    
    Args:
        input_string: The string to encrypt
        encryption_enabled: Whether to perform encryption (if False, returns input as-is)
        
    Returns:
        The encrypted string in the format: morphedKey + separator + morphedIv + 
        separator + dynamicPadding + encryptedString
    """
    if not encryption_enabled:
        return input_string
    
    # Generate random key and IV
    key_string = _get_random_alphanumeric_string(KEY_LENGTH)
    iv_string = _get_random_alphanumeric_string(IV_LENGTH)
    
    # Convert to bytes
    key = key_string.encode('utf-8')
    iv = iv_string.encode('utf-8')
    
    # Encrypt using AES CBC (CryptoJS uses base64 encoding)
    
    if _USE_PYCRYPTODOME:
        # Using pycryptodome
        cipher = AES.new(key, AES.MODE_CBC, iv)
        encrypted_bytes = cipher.encrypt(pad(input_string.encode('utf-8'), AES.block_size))
    else:
        # Using cryptography library
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(input_string.encode('utf-8'))
        padded_data += padder.finalize()
        
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()
    
    # CryptoJS.toString() returns base64-encoded string
    encrypted_string = base64.b64encode(encrypted_bytes).decode('utf-8')
    
    # Morph the key and IV
    morphed_key = _morph_string(key_string)
    morphed_iv = _morph_string(iv_string)
    
    # Generate dynamic padding
    dynamic_padding = _get_random_alphanumeric_string(DYNAMIC_PADDING_LENGTH)
    
    # Combine: morphedKey + separator + morphedIv + separator + dynamicPadding + encryptedString
    return f"{morphed_key}{SEPARATOR}{morphed_iv}{SEPARATOR}{dynamic_padding}{encrypted_string}"


def decrypt(encrypted_data: str, encryption_enabled: bool = True) -> str:
    """
    Decrypt a string that was encrypted using the encrypt function.
    
    This function matches the JavaScript decryption implementation exactly.
    
    Args:
        encrypted_data: The encrypted string to decrypt
        encryption_enabled: Whether decryption is needed (if False, returns input as-is)
        
    Returns:
        The decrypted string
    """
    if not encryption_enabled:
        return encrypted_data
    
    # Split by separator
    parts = encrypted_data.split(SEPARATOR)
    if len(parts) != 3:
        raise ValueError(f"Invalid encrypted data format. Expected 3 parts separated by '{SEPARATOR}'")
    
    morphed_key, morphed_iv, padded_encrypted_string = parts
    
    # Remove dynamic padding (first DYNAMIC_PADDING_LENGTH characters)
    encrypted_string = padded_encrypted_string[DYNAMIC_PADDING_LENGTH:]
    
    # Demorph the key and IV
    key_string = _demorph_string(morphed_key)
    iv_string = _demorph_string(morphed_iv)
    
    # Convert to bytes
    key = key_string.encode('utf-8')
    iv = iv_string.encode('utf-8')
    
    # Decode from base64 (CryptoJS uses base64)
    try:
        encrypted_bytes = base64.b64decode(encrypted_string)
    except Exception as e:
        raise ValueError(f"Failed to decode base64 encrypted string: {e}")
    
    if _USE_PYCRYPTODOME:
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted_data = unpad(cipher.decrypt(encrypted_bytes), AES.block_size)
    else:
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(encrypted_bytes) + decryptor.finalize()
        
        unpadder = padding.PKCS7(128).unpadder()
        decrypted_data = unpadder.update(padded_data)
        decrypted_data += unpadder.finalize()
    
    return decrypted_data.decode('utf-8')

