import os
from flask import Flask, Response
from collector import HostCollector

app = Flask(__name__)

@app.route('/metrics')
def metrics():
    # physical host metrics
    result = HostCollector().do_collect()

    # libvirt metrics
    return Response(result, mimetype='text/plain')


if __name__ == '__main__':
    # pip install libvirt-python
    # pip install pip install prometheus-client
    # pip install flask
    # start_http_server(8999)
    app.run(host='0.0.0.0', port=8999)
