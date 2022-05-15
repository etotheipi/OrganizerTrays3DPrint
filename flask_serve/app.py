from flask import Flask, render_template, redirect, url_for, send_file
from flask_bootstrap import Bootstrap
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField, FloatField, RadioField
from wtforms.validators import DataRequired, InputRequired, ValidationError

import sys
import ast
from hashlib import sha256
import numpy as np

sys.path.append('..')

from gen_tray_png import  draw_tray, base64_encode_file
from create_tray_solidpython import computeBinVolume

app = Flask(__name__)
app.config['SECRET_KEY'] = 'c70ed076fbeccb6230acbc437e6be159'
#from app import views

def validator_is_positive_numeric(form, field):
    try:
        f = float(field.data)
        if f < 0:
            raise
    except:
        raise ValidationError('Input must be a single number, 0.0 or larger')

def validator_xylist_check(form, field):
    if any([c not in '[] ,0123456789' for c in field.data]):
        raise ValidationError('Invalid input: must be comma-separated list of numeric bin sizes')

    try:
        # Safely interpret the user input as a list, if it's valid
        evaled = list(ast.literal_eval(field.data))
        if not all([isinstance(v, (int, float)) for v in evaled]):
            raise
    except Exception as e:
        print(str(e))
        raise ValidationError('Could not parse comma-separated XY list values.')

class GenTrayForm(FlaskForm):
    binary_mm_or_in = RadioField(label='Measurement Units',
                                 choices=[('mm', "mm"), ('in', "inches")],
                                 default='mm')
    x_list = StringField(label='Bin widths (X-axis, mm|in)',
                         description='Comma-separated list in specified units',
                         default="30, 40, 75",
                         validators = [InputRequired(), validator_xylist_check])

    y_list = StringField(label='Bin heights (Y-axis, mm|in)',
                         description='Comma-separated list in specified units',
                         default="20, 30, 45",
                         validators=[InputRequired(), validator_xylist_check])

    wall_thickness = FloatField(label="Wall Thickness (mm, in)",
                                default=1.8,
                                validators=[InputRequired(), validator_is_positive_numeric])
    tray_depth = FloatField(label="Total Tray Depth (mm, in)",
                            default=25,
                            validators=[InputRequired(), validator_is_positive_numeric])
    floor_round = FloatField(label="Roundness of bin floors (mm, in)",
                             default=12,
                             validators=[InputRequired(), validator_is_positive_numeric])


@app.route('/', methods=('GET', 'POST'))
@app.route('/gentray', methods=('GET', 'POST'))
def gen_tray_form():
    form = GenTrayForm()
    if form.validate_on_submit():
        xlist = ast.literal_eval('['+form.x_list.data.strip('[]')+']')
        ylist = ast.literal_eval('['+form.y_list.data.strip('[]')+']')
        wall = float(form.wall_thickness.data)
        depth = float(form.tray_depth.data)
        rdepth = float(form.floor_round.data)

        vol_mtrx = np.zeros(shape=(len(xlist), len(ylist)))
        for ix,x in enumerate(xlist):
            for iy,y in enumerate(ylist):
                vol_mtrx[ix, iy], _ = computeBinVolume(x, y, depth, rdepth)
                print(vol_mtrx[ix,iy])

        tmp_file = draw_tray(xlist, ylist, wall, vol_mtrx)
        rawb64 = base64_encode_file(tmp_file)

        cmd_args  = f" \\\n   {xlist}"
        cmd_args += f" \\\n   {ylist}"
        cmd_args += f" \\\n   --wall {wall}"
        cmd_args += f" \\\n   --floor {depth}"
        cmd_args += f" \\\n   --round {rdepth}"
        if str(form.binary_mm_or_in.data) == 'in':
            cmd_args += f" \\\n   --inches"

        docker_cmd = "docker run -it -v `pwd`:/mnt etotheipi/3dprint-tray-gen:latest"
        local_cmd = "python3 create_tray_solidpython.py"

        return render_template('input_form.html', form=form, preview=True, preview_b64=rawb64,
                               docker_cmd = docker_cmd + cmd_args,
                               local_cmd = local_cmd + cmd_args)

    return render_template('input_form.html', form=form, preview=False, preview_b64=None)

@app.route('/gen_download_stl', methods=('POST',))
def submit_stl_generate():
    form = GenTrayForm()
    if form.validate_on_submit():
        xlist = ast.literal_eval('['+form.x_list.data+']')
        ylist = ast.literal_eval('['+form.y_list.data+']')
        wall = float(form.wall_thickness.data)
        depth = float(form.tray_depth.data)
        rdepth = float(form.floor_round.data)
        tray_hash = generate_tray_hash(xlist, ylist, wall, depth, rdepth)


def generate_tray_hash(xlist, ylist, wall, depth, rdepth):
    """
    This method generates a unique identifier for a given tray for the given version of this script
    (based on the version.txt file).  This allows us to generate a given tray one time, and then it
    can be saved to a central location and pulled if it is requested again, instead of regenerating.
    """

    to_hash = []
    to_hash.append(open('version.txt', 'r').read().strip())
    to_hash.append(xlist)
    to_hash.append(ylist)
    to_hash.append(wall)
    to_hash.append(depth)
    to_hash.append(rdepth)

    unique_str = '|'.join(to_hash).encode('utf-8')
    return sha256(unique_str).hexdigest()


@app.route('/about', methods=('GET',))
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run()
