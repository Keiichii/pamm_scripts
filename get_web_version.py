import requests
import argparse

def request(url):
    data = error = None
    try:
        response = requests.get(f'http://{url}/revision', timeout=15)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        error = f'Cannot connect: {e}'
    except Exception as e:
        error = e
    else:
        data = response.text
    return data, error


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Request PAMM WEB build version')
    parser.add_argument('URL', help='URL')
    args = parser.parse_args()

    ver, err = request(args.URL)
    if err:
        print(err)
    if ver:
        print(ver)