import os.path

from flask import Flask, render_template, redirect, url_for, send_file, request
from flask_bootstrap import Bootstrap
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField, FloatField, RadioField
from wtforms.validators import DataRequired, InputRequired, ValidationError

import sys
import ast
import numpy as np
import yaml
import time
import logging
import subprocess
import requests


# If you want to hardcode specific AWS profile (in ~/.aws/config or ~/.aws/credentials), then
# you can manaully uncomment and modify the the last line here.  Or run the app with
# AWS_PROFILE=<...> on the CLI.
import boto3
from botocore.exceptions import ClientError
#boto3.setup_default_session(profile_name='default')

logging.basicConfig(filename='gentray_server.log', level=logging.INFO)
logging.info('Starting server...')

sys.path.append('..')

# Used to find
THIS_SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
S3BUCKET = 'etotheipi-gentray-store'

from gen_tray_png import draw_tray, base64_encode_file
from generate_tray import compute_bin_volume, generate_tray_hash, check_status

app = Flask(__name__)
app.config['SECRET_KEY'] = 'c70ed076fbeccb6230acbc437e6be159'

def validator_is_positive_numeric(form, field):
    try:
        f = float(field.data)
        if f < 0:
            raise
    except:
        errstr = 'Input must be a single, positive value'
        logging.error(errstr)
        raise ValidationError(errstr)

def validator_xylist_check(form, field):
    if any([c not in '[] ,0123456789' for c in field.data]):
        errstr = 'Invalid input: must be comma-separated list of numeric bin sizes'
        logging.error(errstr)
        raise ValidationError(errstr)

    try:
        # Safely interpret the user input as a list, if it's valid
        evaled = list(ast.literal_eval(field.data))
        if not all([isinstance(v, (int, float)) for v in evaled]):
            raise
    except Exception as e:
        errstr = 'Could not parse comma-separated XY list values.'
        logging.error(errstr)
        logging.error(str(e))
        raise ValidationError(errstr)

class GenTrayForm(FlaskForm):
    binary_mm_or_in = RadioField(label='Units for all inputs:',
                                 choices=[('mm', "mm"), ('in', "inches")],
                                 default='mm')

    x_list = StringField(label='Bin X-sizes (in selected units)',
                         description='Comma-separated list in specified units',
                         default="30, 40, 75",
                         validators = [InputRequired(), validator_xylist_check])

    y_list = StringField(label='Bin Y-sizes (in selected units)',
                         description='Comma-separated list in specified units',
                         default="20, 30, 45",
                         validators=[InputRequired(), validator_xylist_check])

    tray_depth = FloatField(label="Center depth of bins (in selected units)",
                            default=25,
                            validators=[InputRequired(), validator_is_positive_numeric])

    wall_thickness = FloatField(label="Wall Thickness (in selected units)",
                                default=1.8,
                                validators=[InputRequired(), validator_is_positive_numeric])

    floor_thickness = FloatField(label="Thickness of floor (in selected units)",
                                 default=1.8,
                                 validators=[InputRequired(), validator_is_positive_numeric])

    floor_round = FloatField(label="Roundness of bin floors (in selected units)",
                             default=12,
                             validators=[InputRequired(), validator_is_positive_numeric])


@app.route('/', methods=('GET', 'POST'))
def redirect_root():
    return redirect(url_for('gen_tray_form'))

@app.route('/gentray', methods=('GET', 'POST'))
def gen_tray_form():
    logging.info("gen_tray_form called")
    form = GenTrayForm()
    #if form.validate_on_submit():
    if form.is_submitted():
        RESCALE = 1 if str(form.binary_mm_or_in.data) == 'mm' else 25.4

        xlist = ast.literal_eval('['+form.x_list.data.strip('[]')+']')
        ylist = ast.literal_eval('['+form.y_list.data.strip('[]')+']')
        xlist = [RESCALE * x for x in xlist]
        ylist = [RESCALE * y for y in ylist]

        depth = float(form.tray_depth.data) * RESCALE
        wall = float(form.wall_thickness.data) * RESCALE
        floor = float(form.floor_thickness.data) * RESCALE
        round = float(form.floor_round.data) * RESCALE

        input_dict = {
            'xlist': xlist,
            'ylist': ylist,
            'depth': depth,
            'wall': wall,
            'floor': floor,
            'round': round,
        }

        logging.info(yaml.dump(input_dict, indent=2))

        vol_mtrx = np.zeros(shape=(len(xlist), len(ylist)))
        for ix,x in enumerate(xlist):
            for iy,y in enumerate(ylist):
                vol_mtrx[ix, iy], _ = compute_bin_volume(x, y, depth, round)

        tmp_file = draw_tray(xlist, ylist, wall, vol_mtrx, floor=floor, depth=depth)
        rawb64 = base64_encode_file(tmp_file)

        cmd_args  = f" \\\n   {xlist}"
        cmd_args += f" \\\n   {ylist}"
        cmd_args += f" \\\n   --depth {depth}"
        cmd_args += f" \\\n   --wall {wall}"
        cmd_args += f" \\\n   --floor {floor}"
        cmd_args += f" \\\n   --round {round}"
        cmd_args += f" \\\n   --yes"

        docker_cmd = "docker run -it -v `pwd`:/mnt etotheipi/3dprint-tray-gen:latest"
        local_cmd = "python3 generate_tray.py"

        if 'preview_only' in request.form:
            return render_template('input_form.html', form=form, preview=True, preview_b64=rawb64,
                                   docker_cmd=docker_cmd + cmd_args,
                                   local_cmd=local_cmd + cmd_args)
        elif 'generate_stl' in request.form:
            return redirect(url_for('process_stl_request'), code=307)

    return render_template('input_form.html', form=form, preview=False, preview_b64=None)

@app.route('/process_stl_request', methods=('POST',))
def process_stl_request():
    form = GenTrayForm()
    if form.is_submitted():
        xlist = ast.literal_eval('['+form.x_list.data.strip('[]')+']')
        ylist = ast.literal_eval('['+form.y_list.data.strip('[]')+']')
        depth = float(form.tray_depth.data)
        wall = float(form.wall_thickness.data)
        floor = float(form.floor_thickness.data)
        round = float(form.floor_round.data)
        tray_hash = generate_tray_hash(xlist, ylist, depth, wall, floor, round)

        # This is in the flask_serve directory, need to go up one level for the create script
        root_dir = os.path.dirname(THIS_SCRIPT_PATH)
        call_args = [
            sys.executable,  # the python interpreter running this script
            os.path.join(root_dir, 'generate_tray.py'),
            f'[{",".join([str(x) for x in xlist])}]',
            f'[{",".join([str(y) for y in ylist])}]',
            '--depth', str(depth),
            '--wall', str(wall),
            '--floor', str(floor),
            '--round', str(round),
            '--s3bucket', S3BUCKET,
            '--s3dir', tray_hash,
            '--yes'
        ]
        logging.info('Creating subprocess with:' + '|'.join(call_args))

        # Starts this process in the background and continues immediately
        subprocess.Popen(call_args, cwd=root_dir)
        time.sleep(1)

        redir_url = url_for('download_status_wait', tray_hash=tray_hash)
        return redirect(redir_url)
    else:
        raise IOError("No form data submitted to process_stl_request(form)")


@app.route('/download_status_wait/<tray_hash>', methods=('GET',))
def download_status_wait(tray_hash):
    dl_status = check_status(S3BUCKET, tray_hash)
    logging.info(yaml.dump(dl_status, indent=2))

    if dl_status['status'].lower() == 'dne':  # Nothing exists yet
        return render_template('download_stl.html',
                               wait_for_download=True,
                               is_complete=False,
                               message="Request submitted to generate tray.",
                               tray_hash=tray_hash)


    tmp_file = draw_tray(
        dl_status['params']['xlist'],
        dl_status['params']['ylist'],
        dl_status['params']['wall'],
        vol_mtrx_ml=None,
        floor=dl_status['params']['floor'],
        depth=dl_status['params']['depth'])

    rawb64 = base64_encode_file(tmp_file)

    if dl_status['status'].lower() == 'initiated':
        return render_template('download_stl.html',
                               wait_for_download=True,
                               is_complete=False,
                               preview_b64=rawb64,
                               message="Tray is being generated.  Please wait...",
                               params=dl_status['params'],
                               tray_hash=tray_hash)
    elif dl_status['status'].lower() == 'complete':
        return render_template('download_stl.html',
                               wait_for_download=True,
                               is_complete=True,
                               preview_b64=rawb64,
                               message="Tray generation complete!  Use the download link below",
                               params=dl_status['params'],
                               tray_hash=tray_hash)
    elif dl_status['status'].lower() == 'failed':
        return render_template('download_stl.html',
                               wait_for_download=False,
                               is_complete=False,
                               params=dl_status['params'],
                               tray_hash=tray_hash)


@app.route('/about', methods=('GET',))
def about():
    return render_template('about.html')

def flask_app():
    return app

if __name__ == '__main__':
    app.run(port=5000, host='0.0.0.0')


