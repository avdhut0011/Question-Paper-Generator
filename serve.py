#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QPG Network Server - Waitress Production Server
Created by Avadhut Jagtap

This script serves the QPG application using Waitress WSGI server,
enabling access from other computers on the network.
"""

import os
import sys
import socket
import logging
import argparse
from waitress import serve
from app import app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('qpg_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("QPG-Server")

def get_local_ip():
    """Get the local IP address of the machine."""
    try:
        # Connect to a remote address to determine local IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        return local_ip
    except Exception:
        return "127.0.0.1"

def validate_environment():
    """Validate that all required environment variables are set."""
    required_vars = ['DATABASE_URL', 'FLASK_SECRET_KEY']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Configure PostgreSQL and the signing secret. See README.md.")
        return False
    
    return True

def print_server_info(host, port):
    """Print server startup information."""
    local_ip = get_local_ip()
    
    print("\n" + "="*60)
    print("QPG Server Starting")
    print("="*60)
    print(f"Application: Question Paper Generator")
    print(f"Created by: Avadhut Jagtap")
    print(f"Server: Waitress WSGI Server")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print("\nAccess URLs:")
    print(f"   Local:    http://localhost:{port}")
    print(f"   Local:    http://127.0.0.1:{port}")
    if local_ip != "127.0.0.1":
        print(f"   Network:  http://{local_ip}:{port}")
    print(f"   Network:  http://{host}:{port}")
    print("\nServer Configuration:")
    print(f"   Threads: 4")
    print(f"   Connection Limit: 1000")
    print(f"   Cleanup Interval: 30s")
    print(f"   Channel Timeout: 120s")
    print("\nNetwork Access Instructions:")
    print("   1. Ensure firewall allows connections on the specified port")
    print("   2. Other devices should use the Network URL to access QPG")
    print("   3. All devices must be on the same network")
    print("\nTo stop the server: Press Ctrl+C")
    print("="*60)
    print("[OK] Server is ready for connections...")
    print("="*60 + "\n")

def main():
    """Main server function."""
    parser = argparse.ArgumentParser(
        description="QPG Network Server - Serve QPG application on network",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python serve.py                          # Default: 0.0.0.0:8080
  python serve.py --port 5000              # Custom port
  python serve.py --host 192.168.1.100    # Specific IP
  python serve.py --host 0.0.0.0 --port 3000 --threads 8
  
Network Access:
  - Use 0.0.0.0 as host to allow access from any network interface
  - Use specific IP to restrict access to that interface only
  - Ensure firewall allows connections on the specified port
        """
    )
    
    parser.add_argument(
        '--host', 
        default='0.0.0.0',
        help='Host IP address (default: 0.0.0.0 - all interfaces)'
    )
    
    parser.add_argument(
        '--port', 
        type=int, 
        default=8080,
        help='Port number (default: 8080)'
    )
    
    parser.add_argument(
        '--threads', 
        type=int, 
        default=4,
        help='Number of threads (default: 4)'
    )
    
    parser.add_argument(
        '--debug', 
        action='store_true',
        help='Enable debug mode'
    )
    
    parser.add_argument(
        '--quiet', 
        action='store_true',
        help='Suppress startup messages'
    )
    
    args = parser.parse_args()
    
    # Validate environment
    if not validate_environment():
        sys.exit(1)
    
    # Configure Flask app
    app.config['ENV'] = 'development' if args.debug else 'production'
    app.config['DEBUG'] = args.debug
    
    # Print server information
    if not args.quiet:
        print_server_info(args.host, args.port)
    
    try:
        # Start the Waitress server
        logger.info(f"Starting QPG server on {args.host}:{args.port}")
        
        serve(
            app,
            host=args.host,
            port=args.port,
            threads=args.threads,
            connection_limit=1000,
            cleanup_interval=30,
            channel_timeout=120,
            max_request_body_size=33554432,  # 32MB
            expose_tracebacks=args.debug,
            ident='QPG-Server/1.0'
        )
        
    except KeyboardInterrupt:
        print("\n\nServer shutdown requested by user")
        logger.info("Server shutdown by user interrupt")
        
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\n[ERROR] Port {args.port} is already in use")
            print(f"Try a different port: python serve.py --port {args.port + 1}")
        else:
            print(f"\n[ERROR] Network Error: {e}")
        logger.error(f"Server startup failed: {e}")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n[ERROR] Unexpected Error: {e}")
        logger.error(f"Unexpected server error: {e}")
        sys.exit(1)
        
    finally:
        print("\n[OK] QPG Server stopped gracefully")
        logger.info("QPG Server stopped")

if __name__ == "__main__":
    main()