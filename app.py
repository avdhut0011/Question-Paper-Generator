"""Ashoka school platform entry point. Configure PostgreSQL before starting."""
from school_platform import create_app

app = create_app()


def main():
    import argparse
    from waitress import serve
    parser = argparse.ArgumentParser(description="Ashoka Assessment Platform")
    parser.add_argument('--browser', action='store_true', help='Compatibility flag; serves the browser platform')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()
    serve(app, host=args.host, port=args.port, threads=4)


if __name__ == '__main__':
    main()
