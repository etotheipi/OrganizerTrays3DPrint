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
from solid import *
from solid.utils import *
from ast import literal_eval
from math import sqrt, pi
import os
import time
import sys
import argparse
import subprocess

xScale = 1.0
yScale = 1.0
zScale = 1.0


################################################################################
# This will create a plug that can be subtracted from the tray frame/box
def create_subtract_slot(
          offsetX,
          offsetY,
          sizeX,
          sizeY,
          binDepth,
          roundDepth=15,
          trayFloor=1.5):

    sizeX = float(sizeX)
    sizeY = float(sizeY)

    # If round-depth is zero, it's just a square plug
    if roundDepth<=0:
        return translate([offsetX, offsetY, trayFloor]) \
                 ( 
                     cube([sizeX, sizeY, depth*1.1])
                 )

    # Create 1:1 aspect, then stretch the whole thing at once 
    # Prism sitting with corner at origin
    fullPrism = cube([sizeX, sizeX, depth*1.1])


    # Prism translated in the z-dir by the roundDepth
    partPrism = translate([0, 0, roundDepth]) \
                    ( 
                        cube([sizeX, sizeX, depth*1.1])
                    )


    # Start by creating a sphere in the center, scale it in y- an z-, then
    # translate it to the bottom of the partPrism
    sphereRad = sqrt(2)*sizeX/2.0
    sphereScaleZ = roundDepth/sphereRad

    theSphere = translate([sizeX/2.0, sizeX/2.0, roundDepth]) \
                    ( 
                        scale([1, 1, sphereScaleZ]) \
                        (
                            sphere(sphereRad)
                        )
                    )

    
    return translate([offsetX, offsetY, trayFloor]) \
             ( 
                 scale([1, sizeY/sizeX, 1]) \
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
def computeBinVolume(xsz, ysz, depth, rdepth):
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
    sphereScaleZ = rdepth / sphereRad

    a = xsz / 2.0
    h = sphereRad - a
    oneCapFullVol  = pi * h * (3*a*a + h*h) / 6.0

    fullSphereVol = 4.0 * pi * sphereRad**3 / 3.0

    roundVol_mm3  = (fullSphereVol - 4*oneCapFullVol) / 2.0
    roundVol_mm3 *= sphereScaleY
    roundVol_mm3 *= sphereScaleZ

    prismTop_mm3 = (depth - rdepth) * xsz * ysz
    totalVol_mm3 = prismTop_mm3 + roundVol_mm3

    # Now convert to both cups and mL (imperial and metric)
    totalVol_cm3  = totalVol_mm3 / 10**3
    totalVol_mL    = totalVol_cm3              # 1 cm3 == 1 mL  !
    totalVol_cups = totalVol_mm3 / 236588.

    return [totalVol_mL, totalVol_cups]

    
    
def createTray(xlist, ylist, dep, rdep=15, wall=1.5, floor=1.5):

    # Create all the slots to be subtracted from the frame of the tray.
    slots = [] 
    xOff = wall
    yOff = wall

    for ysz in ylist:
        xOff = wall
        for xsz in xlist:
            slots.append(create_subtract_slot(xOff, yOff, xsz, ysz, dep, rdep, floor))
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




if __name__=="__main__":
    
    descr = """
    Create generic trays with rounded bin floors.

    NOTE:  ALL DIMENSIONS ARE IN MILLIMETERS (mm). 
    If your dimensions are inches then simply multiply by 25 to get approx mm
    values (25.4 to be exact).  So 25 mm is about 1 in, 200 mm is about 8 inches. 

    """

    #parser = argparse.ArgumentParser(usage=f"%(prog)\n", description=descr)
    parser = argparse.ArgumentParser(usage=f"<create_tray.py> [options]\n", description=descr)

    #parser.add_argument("xsizes", help="Widths of columns, \"[A,B,C,...]\"")
    #parser.add_argument("ysizes", help="Heights of rows, \"[A,B,C,...]\"")
    parser.add_argument("bin_sizes", nargs='*')

    parser.add_argument("--depth",
                        dest="depth",
                        default=None,
                        type=float, 
                        help="Depth of the tray above floor (mm, default 32)")

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

    parser.add_argument("--round",
                        dest="rdepth",
                        default=None,
                        type=float, 
                        help="Height of tapered bottom (mm, default 12)")

    parser.add_argument("--outfile",
                        dest="outfile",
                        default='',
                        type=str, 
                        help="The output name of the resultant file")

    parser.add_argument("--inches",
                        dest="unit_is_inches",
                        action='store_true',
                        help="Interpret all user inputs as inches (default: mm)")

    parser.add_argument("--yes",
                        dest="skip_prompts",
                        action='store_true',
                        help="Skip prompts (for running headless)")

    args = parser.parse_args()
    print(args)

    MM2IN = 25.4
    RESCALE = MM2IN if args.unit_is_inches else 1.0
    
    # These are not set in the add_argument calls because we need to rescale
    # and don't know if they are use-supplied or default values.  
    if args.floor is None:
        args.floor = 1.8 / RESCALE

    if args.depth is None:
        args.depth = 32.0 / RESCALE

    if args.wall is None:
        args.wall = 1.8 / RESCALE

    if args.rdepth is None:
        args.rdepth = 12.0 / RESCALE


    
    # If you want to specify the args directly here instead of using the CLI, 
    # set the following line to False then hardcode params in the "else:" clause
    USE_CLI_ARGS = True


    if USE_CLI_ARGS:
        floor  = args.floor * RESCALE
        wall   = args.wall * RESCALE
        depth  = args.depth * RESCALE
        rdepth = args.rdepth * RESCALE
        fname  = args.outfile
        try:
            size_args = ''.join(args.bin_sizes)
            size_args = size_args.replace(' ','').replace('][', '],[')
            xsizes, ysizes = literal_eval(size_args)
            xsizes = [RESCALE * x for x in xsizes]
            ysizes = [RESCALE * y for y in ysizes]
        except Exception as e:
            print('Must provide sizes of bins as comma-separated list using square-brackets')
            print('Example:')
            print(f'   {sys.argv[0]} [10, 20,30] [35,45, 55]')
            exit(1)
    else:
        # Example for replacing the above lines if you don't want to use CLI (in mm)
        floor  = 1.5
        wall   = 1.5
        depth  = 40
        rdepth = 15
        xsizes = [30,45,60]
        ysizes = [50,50,50,50]
    
    
    if rdepth > depth-3:
        print( '***Warning:  round depth needs to be at least 3mm smaller than bin depth')

        if not args.skip_prompts:
            ok = input('Shorten round depth? [Y/n]: ')
        else:
            ok = 'yes'

        if ok.lower().startswith('n'):
            print( 'Aborting...')
            exit(1)
        else:
            rdepth = max(depth-3, 0)

    xszStrs = [str(int(x)) for x in xsizes]
    yszStrs = [str(int(y)) for y in ysizes]
    
    print(f'Floor: {floor:.1f} mm  / {floor/MM2IN:.3f} in')
    print(f'Wall:  {wall:.1f} mm   / {wall/MM2IN:.3f} in')
    print(f'Depth: {depth:.1f} mm  / {depth/MM2IN:.2f} in')
    print(f'Round: {rdepth:.1f} mm / {rdepth/MM2IN:.2f} in')

    print('Widths:  [' + ', '.join([f'{x:.1f}' for x in xsizes]) + '] mm')
    print('Heights: [' + ', '.join([f'{y:.1f}' for y in ysizes]) + '] mm')
    print('Widths:  [' + ', '.join([f'{x/MM2IN:.2f}' for x in xsizes]) + '] in')
    print('Heights: [' + ', '.join([f'{y/MM2IN:.2f}' for y in ysizes]) + '] in')

    # If you don't override fname, the scad file will automatically be named
    if not fname:
        fname = 'tray_%s_by_%s.scad' % ('x'.join(xszStrs), 'x'.join(yszStrs))

    # Now tell solid python to create the .scad file
    print('Writing to OpenSCAD file:', fname)
    twid,thgt,trayObj = createTray(xsizes,ysizes, depth, rdepth, wall, floor)
    scad_render_to_file(trayObj, fname, file_header='$fn=64;')

    

    ################################################################################
    # EVERYTHING BELOW THIS LINE IS SIMPLY FOR PRINTING ASCII DIAGRAMS
    # Print some useful info
    print(f'Tray size is: {twid:.2f}mm by {thgt:.2f}mm')
    print(f'Tray size is: {twid/MM2IN:.2f}in by {thgt/MM2IN:.2f}in')
    

    # The diagram will be approximately 72 chars wide by 48 chars tall
    # Console letters are about 1.5 times taller than they are wide
    totalCharsWide = 82
    totalCharsHigh = float(thgt)/float(twid) * (totalCharsWide/2.0)
    
    def getCharsWide(mm):
        maxInternalChars = totalCharsWide - (len(xsizes)+1)
        return max(10, int(maxInternalChars*float(mm)/float(twid)))
            
    def getCharsHigh(mm):
        maxInternalChars = totalCharsHigh - (len(ysizes)+1)
        return max(2, int(maxInternalChars*float(mm)/float(thgt)))
    
    
    xchars = [getCharsWide(x) for x in xsizes]
    ychars = [getCharsHigh(y) for y in ysizes]
    
    print( '')
    print( '')
    
    
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
                mL,cups = computeBinVolume(xsizes[i], ysizes[revj], depth, rdepth)
        
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
    
    print(f'Total Width  (with walls):  {twid:.2f} mm \t /  {twid/MM2IN:.2f} in')
    print(f'Total Height (with walls):  {thgt:.2f} mm \t /  {thgt/MM2IN:.2f} in')
    print(f'Total Depth  (with floor):  {depth+floor:.2f} mm \t /  {(depth+floor)/MM2IN:.2f} in')
    print('')

    if not args.skip_prompts:
        ok = input('Generate STL file? (this can take a few minutes) [N/y]: ')
    else:
        ok = 'yes'

    if ok.lower().startswith('y'):
        stlname = fname+'.stl'
        print('Converting to STL file:', stlname)
        proc = subprocess.Popen('openscad -o "%s" "%s"' % (stlname, fname), shell=True)
        while proc.poll()==None:
            time.sleep(0.1)








