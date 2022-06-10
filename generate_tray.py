#! /usr/bin/python
"""
ALL UNITS ARE MILLIMETERS

The tray will be specified by the dimensions of each row & column,
provided as two arrays.  If your bin is going to look like this:

                  ----------------------------------
                  |              |      |          |
          60mm    |              |      |          |
                  ----------------------------------
                  |              |      |          |
          60mm    |              |      |          |
                  ----------------------------------
                  |              |      |          |
                  |              |      |          |
         100mm    |              |      |          |
                  ----------------------------------
          30mm    |              |      |          |
                  ----------------------------------
                         40mm        25mm      70mm        


Use the following command-line call to generate the above (x-axis always first)
You can add extra -- args to adjust floor- and wall-thickness, as well as
bin depth and how rounded you want the bins to be on the bottom.
Make sure there are no spaces before or after the commas in the lists:

    python create_tray_solidpython.py [40,25,70] [30,100,60,60] 
    python create_tray_solidpython.py [40,25,70] [30,100,60,60] --depth=55 --wall=1.5

Type the following to see all options:

    python create_tray_solidpython.py --help

                
"""
import copy
import io

from solid import *
from solid.utils import *
from ast import literal_eval
from math import sqrt, pi
from hashlib import sha256
import os
import io
import time
import sys
import argparse
import subprocess
import requests
import tempfile
import yaml
import logging


logging.basicConfig(filename='gentray_script.log', level=logging.INFO)
logging.info('Starting generate script')

# A simple method that dumps log messages to both the terminal and logfile
def LOG_IT(*strs):
    sstrs = [str(s) for s in strs]
    print(*sstrs)
    logging.info(' '.join(sstrs))


xScale = 1.0
yScale = 1.0
zScale = 1.0


################################################################################
# This will create a plug that can be subtracted from the tray frame/box
def create_subtract_slot(x_offset, y_offset, x_size, y_size, depth, floor, round):

    x_size = float(x_size)
    y_size = float(y_size)

    # If round-depth is zero, it's just a square plug
    if round<=0:
        return translate([x_offset, y_offset, floor]) \
                 ( 
                     cube([x_size, y_size, depth*1.1])
                 )

    # Create 1:1 aspect, then stretch the whole thing at once 
    # Prism sitting with corner at origin
    fullPrism = cube([x_size, x_size, depth*1.1])


    # Prism translated in the z-dir by the round
    partPrism = translate([0, 0, round]) \
                    ( 
                        cube([x_size, x_size, depth*1.1])
                    )


    # Start by creating a sphere in the center, scale it in y- an z-, then
    # translate it to the bottom of the partPrism
    sphereRad = sqrt(2)*x_size/2.0
    sphereScaleZ = round/sphereRad

    theSphere = translate([x_size/2.0, x_size/2.0, round]) \
                    ( 
                        scale([1, 1, sphereScaleZ]) \
                        (
                            sphere(sphereRad)
                        )
                    )

    
    return translate([x_offset, y_offset, floor]) \
             ( 
                 scale([1, y_size/x_size, 1]) \
                 (
                     intersection() \
                     ( 
                         fullPrism,
                         union() \
                         ( 
                             partPrism,
                             theSphere 
                         )
                     )
                 )
             )


################################################################################
def compute_bin_volume(xsz, ysz, depth, round):
    """
    UPDATED:  Now we do this calculation exactly.  We compute the volume of the 
    prism and then compute the volume of the hemisphere.  The hemisphere is 
    complex because it's actually a hemisphere intersected with a square peg.  

    We do the volume calculation by computing the volume of the full hemisphere 
    and then subtracting the volume of the four "spherical caps".    At once we
    have that, we scale the volume by both the y-scale and z-scale.

    From http://en.wikipedia.org/wiki/Spherical_cap the volume of a spherical
    cap is:

        pi * h * (3a*a + h*h) / 6

    "h" is the height of the cap which is the radius of sphere minus x/2
    "a" is the radius of the base of the cap, which is just x/2

    Don't forget to cut the resultant sph cap volume in half, because we're
    only removing half of a cap (because it's from half a hemisphere)
    """
    
    # 
    sphereRad     = sqrt(2) * xsz / 2.0
    sphereScaleY = ysz / xsz
    sphereScaleZ = round / sphereRad

    a = xsz / 2.0
    h = sphereRad - a
    oneCapFullVol  = pi * h * (3*a*a + h*h) / 6.0

    fullSphereVol = 4.0 * pi * sphereRad**3 / 3.0

    roundVol_mm3  = (fullSphereVol - 4*oneCapFullVol) / 2.0
    roundVol_mm3 *= sphereScaleY
    roundVol_mm3 *= sphereScaleZ

    prismTop_mm3 = (depth - round) * xsz * ysz
    totalVol_mm3 = prismTop_mm3 + roundVol_mm3

    # Now convert to both cups and mL (imperial and metric)
    totalVol_cm3  = totalVol_mm3 / 10**3
    totalVol_mL    = totalVol_cm3              # 1 cm3 == 1 mL  !
    totalVol_cups = totalVol_mm3 / 236588.

    return [totalVol_mL, totalVol_cups]


def generate_tray_hash(xlist, ylist, depth, wall, floor, round):
    """
    This method generates a unique identifier for a given tray for the given version of this script
    (based on the version.txt file).  This allows us to generate a given tray one time, and then it
    can be saved to a central location and pulled if it is requested again, instead of regenerating.
    """
    to_hash = []

    if os.path.exists('version.txt'):
        to_hash.append(open('version.txt', 'r').read().strip())

    to_hash.append(','.join([str(x) for x in xlist]))
    to_hash.append(','.join([str(y) for y in ylist]))
    to_hash.append(str(floor))
    to_hash.append(str(wall))
    to_hash.append(str(depth))
    to_hash.append(str(round))

    unique_str = '|'.join(to_hash).encode('utf-8')
    hash_str = sha256(unique_str).hexdigest()
    LOG_IT('Value hashed for ID:', unique_str)
    LOG_IT('Hash value for tray:', hash_str)
    return hash_str


def createTray(xlist, ylist, depth=28, wall=1.5, floor=1.5, round=15):

    # Create all the slots to be subtracted from the frame of the tray.
    slots = [] 
    xOff = wall
    yOff = wall

    for ysz in ylist:
        xOff = wall
        for xsz in xlist:
            slots.append(create_subtract_slot(xOff, yOff, xsz, ysz, depth, floor, round))
            xOff += wall + xsz
        yOff += wall + ysz

    # The loops leave xOff & yOff at the upper-left corner of the tray.  Perfect!
    totalWidth  = xOff
    totalHeight = yOff
    
    # We have a list of "slots", unionize them.
    allStuffToSubtract = union()(*slots)
    
    # Create the prism from which the slots will be subtracted
    trayBasePrism = cube([totalWidth, totalHeight, floor+depth])

    # Finally, create the object and scale by the printer-calibration data
    return [totalWidth, totalHeight, 
              scale([xScale, yScale, zScale]) \
              ( 
                  difference() \
                  ( 
                      trayBasePrism,
                      allStuffToSubtract
                  ) 
              )]


# Only if there is
def upload_status(params, status, message, s3obj):
    s3client = boto3.client('s3')
    upload_params = copy.deepcopy(params)
    stat_file = {
        'status': status,
        'message': message,
        'params': upload_params
    }

    with tempfile.TemporaryFile() as fp:
        fp.write(yaml.dump(stat_file, indent=2).encode('utf-8'))
        fp.seek(0)
        s3client.upload_fileobj(fp, args.s3bucket, s3obj, ExtraArgs={'ContentType': 'text/plain', 'ACL': 'public-read'})

# Only if there is
def check_status(s3bucket, s3dir):
    s3_download = f'https://{s3bucket}.s3.amazonaws.com/{s3dir}/status.txt'
    status_file_obj = requests.get(s3_download)
    if status_file_obj.status_code != 200:
        return {'status': 'DNE'}
    else:
        LOG_IT("Getting status file to see if it has already been created:", s3_download)
        status_dict = yaml.safe_load(status_file_obj.content)
        return status_dict




if __name__=="__main__":
    descr = """
    Create generic trays with rounded bin floors.

    NOTE:  ALL DIMENSIONS ARE IN MILLIMETERS (mm). 
    If your dimensions are inches then simply multiply by 25 to get approx mm
    values (25.4 to be exact).  So 25 mm is about 1 in, 200 mm is about 8 inches. 
    
    EXAMPLES:
       $ python3 generate_tray.py [x0, x1, ...] [y0, y1, ...] <options>
       $ python3 generate_tray.py [15,25,35] [30,40,50,60]
       $ python3 generate_tray.py [25] [50,50,50,50] --depth=20 --wall=2.5 --floor=2 --round=12
       
       
    NOTE: Total tray height is depth+floor.
    """

    #parser = argparse.ArgumentParser(usage=f"%(prog)\n", description=descr)
    parser = argparse.ArgumentParser(usage=f"python3 generate_tray.py [options]\n", description=descr)
    parser.add_argument("bin_sizes", nargs='*')

    parser.add_argument("--floor",
                        dest="floor",
                        default=None,
                        type=float, 
                        help="Thickness of tray floor (mm, default 1.8)")

    parser.add_argument("--wall",
                        dest="wall",
                        default=None,
                        type=float, 
                        help="Thickness of walls (mm, default 1.8)")

    parser.add_argument("--depth",
                        dest="depth",
                        default=None,
                        type=float,
                        help="Depth of the tray above floor (mm, default 32)")

    parser.add_argument("--round",
                        dest="round",
                        default=None,
                        type=float, 
                        help="Height of tapered bottom (mm, default 12)")

    parser.add_argument("-o", '--outfile',
                        dest="outfile",
                        default=None,
                        type=str,
                        help="The output name of the resultant file (extension will be ignored)")

    parser.add_argument("--inches",
                        dest="unit_is_inches",
                        action='store_true',
                        help="Interpret all user inputs as inches (default: mm)")

    parser.add_argument("--yes",
                        dest="skip_prompts",
                        action='store_true',
                        help="Skip prompts (for running headless)")

    parser.add_argument("--s3bucket",
                        dest='s3bucket',
                        default=None,
                        type=str,
                        help="Put results into s3 bucket using hash locator")

    parser.add_argument("--s3dir",
                        dest='s3dir',
                        default=None,
                        type=str,
                        help="Unique identifier for files to be stored in S3")

    parser.add_argument("--hardcoded-params",
                        dest='hardcoded_params',
                        action='store_true',
                        help="Ignore all other args, use hardcoded values in script")

    args = parser.parse_args()


    LOG_IT(yaml.dump(args.__dict__, indent=2))

    MM2IN = 25.4
    RESCALE = MM2IN if args.unit_is_inches else 1.0
    
    # These are not set in the add_argument calls because we need to rescale
    # and don't know if they are use-supplied or default values.  
    if args.depth is None:
        args.depth = 32.0 / RESCALE

    if args.wall is None:
        args.wall = 1.8 / RESCALE

    if args.floor is None:
        args.floor = 1.8 / RESCALE

    if args.round is None:
        args.round = 12.0 / RESCALE

    if not args.hardcoded_params:
        depth = args.depth * RESCALE
        wall  = args.wall * RESCALE
        floor = args.floor * RESCALE
        round = args.round * RESCALE
        fname = args.outfile
        try:
            size_args = ''.join(args.bin_sizes)
            size_args = size_args.replace(' ','').replace('][', '],[')
            xsizes, ysizes = literal_eval(size_args)
            xsizes = [RESCALE * x for x in xsizes]
            ysizes = [RESCALE * y for y in ysizes]
        except Exception as e:
            LOG_IT('Must provide sizes of bins as comma-separated list using square-brackets')
            LOG_IT('Example:')
            LOG_IT(f'   {sys.argv[0]} [10, 20,30] [35,45, 55]')
            exit(1)
    else:
        # HARDCODED PARAMETERS:  Modify values below and use --hardcoded-params
        depth = 40
        wall  = 1.5
        floor = 1.5
        round = 15
        xsizes = [30,45,60]
        ysizes = [50,50,50,50]
    
    if round > depth-3:
        LOG_IT( '***Warning:  round depth needs to be at least 3mm smaller than bin depth')

        if not args.skip_prompts:
            ok = input('Shorten round depth? [Y/n]: ')
        else:
            ok = 'yes'

        if ok.lower().startswith('n'):
            LOG_IT( 'Aborting...')
            exit(1)
        else:
            round = max(depth-3, 0)

    xszStrs = [str(int(x)) for x in xsizes]
    yszStrs = [str(int(y)) for y in ysizes]
    
    LOG_IT(f'Depth: {depth:.1f} mm  / {depth/MM2IN:.2f} in')
    LOG_IT(f'Wall:  {wall:.1f} mm   / {wall/MM2IN:.3f} in')
    LOG_IT(f'Floor: {floor:.1f} mm  / {floor/MM2IN:.3f} in')
    LOG_IT(f'Round: {round:.1f} mm / {round/MM2IN:.2f} in')

    LOG_IT('Widths:  [' + ', '.join([f'{x:.1f}' for x in xsizes]) + '] mm')
    LOG_IT('Heights: [' + ', '.join([f'{y:.1f}' for y in ysizes]) + '] mm')
    LOG_IT('Widths:  [' + ', '.join([f'{x/MM2IN:.2f}' for x in xsizes]) + '] in')
    LOG_IT('Heights: [' + ', '.join([f'{y/MM2IN:.2f}' for y in ysizes]) + '] in')

    if fname is None:
        os.makedirs('output_trays', exist_ok=True)
        fname = './output_trays/tray_%s_by_%s' % ('x'.join(xszStrs), 'x'.join(yszStrs))

    # Remove any extension since we need to update
    fname = os.path.splitext(fname)[0]
    fn_scad = fname + '.scad'
    fn_stl = fname + '.stl'
    LOG_IT(f'Will write:\n   {fn_scad}\n   {fn_stl}')

    # Now tell solid python to create the .scad file
    LOG_IT('Writing to OpenSCAD file:', fn_scad)
    twid,thgt,trayObj = createTray(xsizes, ysizes, depth, wall, floor, round)
    scad_render_to_file(trayObj, fn_scad, file_header='$fn=64;')

    ################################################################################
    # The next section is simply for printing useful info to the console
    ################################################################################
    LOG_IT(f'Tray size is: {twid:.2f}mm by {thgt:.2f}mm')
    LOG_IT(f'Tray size is: {twid/MM2IN:.2f}in by {thgt/MM2IN:.2f}in')
    
    # The diagram will be approximately 72 chars wide by 48 chars tall
    # Console letters are about 1.5 times taller than they are wide
    totalCharsWide = 82
    totalCharsHigh = float(thgt)/float(twid) * (totalCharsWide/2.0)
    
    def compute_chars_wide(mm):
        maxInternalChars = totalCharsWide - (len(xsizes)+1)
        return max(10, int(maxInternalChars*float(mm)/float(twid)))
            
    def compute_chars_high(mm):
        maxInternalChars = totalCharsHigh - (len(ysizes)+1)
        return max(2, int(maxInternalChars*float(mm)/float(thgt)))
    
    xchars = [compute_chars_wide(x) for x in xsizes]
    ychars = [compute_chars_high(y) for y in ysizes]
    
    LOG_IT('')
    LOG_IT('')

    wCharsTotal = sum(xchars) + len(xchars) + 1
    hCharsTotal = sum(ychars) + len(ychars) + 1
    
    vertLine = ' '*10 + '-' * wCharsTotal + '\n'
    sys.stdout.write(vertLine)
    for j in range(len(ysizes)):
        # Acually do the y-values in reverse since printing to console happens
        # in the negative y-direction.
        revj = len(ysizes) - j - 1
    
        for jc in range(ychars[revj]):
            yhgt = ychars[revj]
            if jc==yhgt//2:
                sys.stdout.write(('%0.1f mm' % ysizes[revj]).center(10) + '|')
            else:
                sys.stdout.write(' '*10 + '|')
    
            for i in range(len(xsizes)):
                mL,cups = compute_bin_volume(xsizes[i], ysizes[revj], depth, round)
        
                if jc==yhgt//2-1:
                    sys.stdout.write(('%0.2f cups' % cups).center(xchars[i]))
                elif jc==yhgt//2:
                    sys.stdout.write(('%0.1f mL' % mL).center(xchars[i]))
                else:
                    sys.stdout.write(' '*(xchars[i]))
                sys.stdout.write('|')
            sys.stdout.write('\n')

        sys.stdout.write(vertLine)

    sys.stdout.write('\n')
    sys.stdout.write(' '*10)
    for i in range(len(xsizes)):
        sizeStr = '%0.1f mm' % xsizes[i]
        sys.stdout.write(sizeStr.center(xchars[i]+1))
    sys.stdout.write('\n\n')
    
    LOG_IT(f'Total Width  (with walls):  {twid:.2f} mm \t /  {twid/MM2IN:.2f} in')
    LOG_IT(f'Total Height (with walls):  {thgt:.2f} mm \t /  {thgt/MM2IN:.2f} in')
    LOG_IT(f'Total Depth  (with floor):  {depth+floor:.2f} mm \t /  {(depth+floor)/MM2IN:.2f} in')
    LOG_IT('')

    param_map = {
        'xlist': xsizes,
        'ylist': ysizes,
        'depth': depth,
        'wall': wall,
        'floor': floor,
        'round': round
    }

    ################################################################################
    # Get confirmation (if not --yes) and then actually do the STL generation
    ################################################################################
    if not args.skip_prompts:
        ok = input('Generate STL file? (this can take a few minutes) [N/y]: ')
    else:
        ok = 'yes'

    if not ok.lower().startswith('y'):
        exit(0)

    # The following section is only relevant if you specified an S3 storage location
    if args.s3bucket is not None:
        import boto3
        from botocore.exceptions import ClientError

        if args.s3dir is None:
            args.s3dir = generate_tray_hash(xsizes, ysizes, depth, wall, floor, round)

        exist_status = check_status(args.s3bucket, args.s3dir)
        if exist_status['status'].lower() != 'dne':  # does-not-exist flag is false == already exists
            LOG_IT(f'Tray already exists.')
            exit(0)

        s3paths = {
            'stl': f'{args.s3dir}/organizer_tray.stl',
            'status': f'{args.s3dir}/status.txt'
        }

        upload_status(param_map,
                      status='Initiated',
                      message=f'Model generation initiated.  Please wait a few minutes.',
                      s3obj=s3paths['status'])

    LOG_IT('Converting to STL file:', fn_stl)

    try:
        proc = subprocess.check_call('openscad -o "%s" "%s"' % (fn_stl, fn_scad), shell=True)
        if args.s3bucket is not None:
            upload_status(param_map,
                          status='Complete',
                          message=f'Model Generation Complete.  You can download the STL now',
                          s3obj=s3paths['status'])
    except Exception as e:
        LOG_IT('Failed to produce model:', str(e))
        conversion_failed = True
        if args.s3bucket is not None:
            upload_status(param_map,
                          status='Failed',
                          message=f'Model generation script return an error: "{str(e)}"',
                          s3obj=s3paths['status'])

    if args.s3bucket is not None:
        try:
            s3client = boto3.client('s3')
            response = s3client.upload_file(fn_stl, args.s3bucket, s3paths['stl'])
        except ClientError as e:
            upload_status(param_map,
                          status='Failed',
                          message=f'Model created but could not be made available for download.  Error: "{str(e)}"',
                          s3obj=s3paths['status'])

