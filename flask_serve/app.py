from flask import Flask, render_template, redirect, url_for, send_file
from flask_bootstrap import Bootstrap
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField, FloatField, RadioField
from wtforms.validators import DataRequired, InputRequired, ValidationError

import sys
import ast
import numpy as np
import yaml
import logging
logging.basicConfig(filename='gentray_server.log', level=logging.DEBUG)
logging.info('Starting server...')

sys.path.append('..')

from gen_tray_png import draw_tray, base64_encode_file
from generate_tray import computeBinVolume

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
        logging(str(e))
        errstr = 'Could not parse comma-separated XY list values.'
        logging.error(errstr)
        raise ValidationError(errstr)

class GenTrayForm(FlaskForm):
    binary_mm_or_in = RadioField(label='Units for all inputs:',
                                 choices=[('mm', "mm"), ('in', "inches")],
                                 default='mm')

    x_list = StringField(label='Bin widths (X-axis, in selected units)',
                         description='Comma-separated list in specified units',
                         default="30, 40, 75",
                         validators = [InputRequired(), validator_xylist_check])

    y_list = StringField(label='Bin heights (Y-axis, in selected units)',
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
                             default=2.4,
                             validators=[InputRequired(), validator_is_positive_numeric])

    floor_round = FloatField(label="Roundness of bin floors (in selected units)",
                             default=12,
                             validators=[InputRequired(), validator_is_positive_numeric])


@app.route('/', methods=('GET', 'POST'))
@app.route('/gentray', methods=('GET', 'POST'))
def gen_tray_form():
    logging.info("gen_tray_form called")
    form = GenTrayForm()
    if form.is_submitted():
        print('Validate on submit...')
        xlist = ast.literal_eval('['+form.x_list.data.strip('[]')+']')
        ylist = ast.literal_eval('['+form.y_list.data.strip('[]')+']')
        depth = float(form.tray_depth.data)
        wall = float(form.wall_thickness.data)
        floor = float(form.floor_thickness.data)
        round = float(form.floor_round.data)

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
                vol_mtrx[ix, iy], _ = computeBinVolume(x, y, depth, round)
                print(vol_mtrx[ix,iy])

        tmp_file = draw_tray(xlist, ylist, wall, vol_mtrx)
        rawb64 = base64_encode_file(tmp_file)

        cmd_args  = f" \\\n   {xlist}"
        cmd_args += f" \\\n   {ylist}"
        cmd_args += f" \\\n   --depth {depth}"
        cmd_args += f" \\\n   --wall {wall}"
        cmd_args += f" \\\n   --floor {floor}"
        cmd_args += f" \\\n   --round {round}"
        if str(form.binary_mm_or_in.data) == 'in':
            cmd_args += f" \\\n   --inches"

        docker_cmd = "docker run -it -v `pwd`:/mnt etotheipi/3dprint-tray-gen:latest"
        local_cmd = "python3 generate_tray.py"
        return render_template('input_form.html', form=form, preview=True, preview_b64=rawb64,
                               docker_cmd=docker_cmd + cmd_args,
                               local_cmd=local_cmd + cmd_args)

    return render_template('input_form.html', form=form, preview=False, preview_b64=None)

@app.route('/gen_download_stl', methods=('POST',))
def submit_stl_generate():
    form = GenTrayForm()
    if form.validate_on_submit():
        xlist = ast.literal_eval('['+form.x_list.data+']')
        ylist = ast.literal_eval('['+form.y_list.data+']')
        depth = float(form.tray_depth.data)
        wall = float(form.wall_thickness.data)
        floor = float(form.floor_thickness.data)
        round = float(form.floor_round.data)
        tray_hash = generate_tray_hash(xlist, ylist, depth, wall, floor, round)



@app.route('/about', methods=('GET',))
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(port=5000, host='0.0.0.0', debug=True)
