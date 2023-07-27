import os, io, sys, shutil
from flask import Flask, render_template, request, jsonify
from services.rete import Rete

ALLOWED_EXTENSIONS = ["SHP", "SHX", "DBF", "SBN", "SBX", "PRJ", "CPG"]
root_folder = '.'
upload_folder = './upload'

app = Flask(__name__)


@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')

@app.errorhandler(404)
def page_not_found(error):
    return render_template('page_not_found.html'), 404

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

def is_shape_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] == "SHP"

@app.route('/api/process', methods=['POST'])
def process_image():
    result = {"log":""}
    files = None
    try:
        files = request.files.getlist('files[]')
    # except Exception.RequestEnityTooLarge as e:
    #    return "ERROR", 413
    except Exception as ex:
        result["log"] += str(ex)
        return result, 500
    if files:
        clear_directory(upload_folder)
        main_file = None
        for file in files:
            filename = file.filename
            filename = os.path.join(upload_folder, filename)
            if allowed_file(filename.upper()):
                file.save(filename)
                if is_shape_file(filename.upper()):
                    main_file = filename

            result["log"] += f"File {file.filename} saved successfully in temp dir.\n"

        if not main_file:
            result["log"] += "File shp absent .\n"
            return result, 400

        result["log"] += f"Analyze and process {main_file}\n"
        # processed_image = Rete(shapeFile=file)
        # image = cv2.imdecode(np.fromstring(file.read(), np.uint8), cv2.IMREAD_COLOR)
        rete = Rete(shapeFile=main_file)
        status = rete.color_streets()
        if not status:
            result["log"] += rete.result["errors"]
            return result, 400

        # clear_directory(upload_folder)
        result['image'] = rete.blob_url
        result['geojson'] = rete.geojson
        return result, 200
    else:
        result['log'] += "\nerror: No file uploaded."
        return result, 400


@app.route('/<patch>')
def _routepatch(patch=None):
    try:
        return render_template(patch + '.html')
    except Exception as e:
        return page_not_found(404)

def clear_directory(directory_path):
    try:
        # check
        if not os.path.exists(directory_path):
            return

        # delete files in directory
        for filename in os.listdir(directory_path):
            file_path = os.path.join(directory_path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
            elif os.path.isdir(file_path):
                # delete recursive
                shutil.rmtree(file_path)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    rootpath = os.path.dirname(__file__)
    upload_folder = os.path.join(rootpath, 'upload')
    app.run(host='0.0.0.0', port=999)
