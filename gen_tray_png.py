import os
import numpy as np
import tempfile
import matplotlib.pyplot as plt
import base64
from matplotlib.patches import Rectangle
from constants import *



def rescale_dims_for_display(
    xlist,
    ylist,
    wall_size,
    max_aspect=1.6,
    max_bin_ratio=3.0,
    max_abs_size=100):
    """
    The output of this method is an updated xlist and ylist to be used for
    displaying the final geometry/image.  The original x- and y-values are
    still used for the text.

    NOTE: I originally tried to do some fancy aspect ratio stuff here to
    make sure sure the image was sane and the text could be displayed
    clearly.  However it got complex and the final image was too distorted,
    leading me to believe it would actually be LESS useful than seeing
    everything scaled as it would be printed.   The downside is that there
    are geometries where this display fails or is difficult to read :shrug:
    """
    
    # Copy the lists, default is to pass out what was passed in
    xlist_adj = xlist[:]
    ylist_adj = ylist[:]
    wall_size_adj = wall_size
    
    x_total = sum(xlist_adj)
    y_total = sum(ylist_adj)

    # Finally let's give it a consistent size 
    abs_scalar = max_abs_size / max(x_total, y_total)
    xlist_adj = [abs_scalar * x for x in xlist_adj]
    ylist_adj = [abs_scalar * y for y in ylist_adj]
    wall_size_adj = abs_scalar * wall_size_adj

    return xlist_adj, ylist_adj, wall_size_adj


def draw_tray(xlist,
              ylist,
              wall_size,
              vol_mtrx_ml=None, # always in mL regardless of x/y/depth/etc units
              depth=None,
              floor=None,
              units='mm',
              out_filename=None):

    # Depth and floor args are provided just to be displayed, not used in computing the drawing
    fig, ax = plt.subplots(figsize=(12, 12))

    if vol_mtrx_ml is not None:
        if (len(xlist), len(ylist)) != tuple(vol_mtrx_ml.shape[:2]):
            err_msg  = f'Input vol_mtrx_ml has shape {vol_mtrx_ml.shape}, does not'
            err_msg += f'match shape of xlist ({len(xlist)}) and ylist ({len(ylist)})'
            raise IOError(err_msg)
    
    # To make things sane 
    xlist_draw, ylist_draw, wall_size_draw = rescale_dims_for_display(xlist, ylist, wall_size)
    
    x_total = sum(xlist_draw) + (len(xlist_draw)+1) * wall_size_draw
    y_total = sum(ylist_draw) + (len(ylist_draw)+1) * wall_size_draw
    x0, y0 = 10, 20
    rect = Rectangle((x0, y0), x_total, y_total, linewidth=0, facecolor='#333333')
    ax.add_patch(rect)
    xoff, yoff = x0+wall_size_draw, y0+wall_size_draw

    for ix,x in enumerate(xlist_draw):
        for iy,y in enumerate(ylist_draw):
            rect = Rectangle((xoff, yoff), x, y, linewidth=0, facecolor='#8888cc')
            ax.add_patch(rect)
            
            if ix == 0:
                if units == 'mm':
                    y_txt = f'{ylist[iy]:.1f} mm\n({ylist[iy] / MM_PER_IN:.2f} in)'
                else:
                    y_txt = f'{ylist[iy]:.2f} in\n({ylist[iy] * MM_PER_IN:.2f} mm)'

                ax.text(x0-1, yoff + ylist[iy]/2, y_txt, ha='right', va='center', size=12)
                
            if vol_mtrx_ml is not None:
                vol_ml = int(vol_mtrx_ml[ix, iy])
                vol_cup = vol_ml / ML_PER_CUP
                ax.text(xoff + x/2,
                        yoff + y/2,
                        f'{vol_ml} mL\n({vol_cup:.2f} cups)',
                        size=12,
                        ha='center',
                        va='center',
                        color='w')
                    
            # Increment y-position for drawing
            yoff += y + wall_size_draw

        # Draw x-label
        if units == 'mm':
            x_txt = f'{xlist[ix]:.1f} mm\n({xlist[ix] / MM_PER_IN:.2f} in)'
        else:
            x_txt = f'{xlist[ix]:.2f} in\n({xlist[ix] * MM_PER_IN:.2f} mm)'

        ax.text(xoff + x/2, y0-1, x_txt, ha='center', va='top', size=12)

        # Reset y-position for drawing, increment x-position
        yoff = y0 + wall_size_draw
        xoff += x + wall_size_draw
        
    # Some summary text
    x_total_real = sum(xlist) + (len(xlist)+1) * wall_size
    y_total_real = sum(ylist) + (len(ylist)+1) * wall_size

    if units == 'mm':
        total_size_txt  =  f'Total Tray Size: {x_total_real:.1f} mm x {y_total_real:.1f} mm'
        total_size_txt +=  f' ({x_total_real / MM_PER_IN:.2f} in x {y_total_real / MM_PER_IN:.2f} in)'
        if None not in [depth, floor]:
            total_size_txt += f'\nTotal Tray Height (depth+floor): {depth + floor:.1f} mm'
            total_size_txt += f' ({(depth + floor)/MM_PER_IN:.2f} in)'
    else:
        total_size_txt  =  f'Total Tray Size: {x_total_real:.1f} in x {y_total_real:.1f} in'
        total_size_txt +=  f' ({x_total_real * MM_PER_IN:.2f} mm x {y_total_real * MM_PER_IN:.2f} mm)'
        if None not in [depth, floor]:
            total_size_txt += f'\nTotal Tray Height (depth+floor): {depth + floor:.1f} in'
            total_size_txt += f' ({(depth + floor) * MM_PER_IN:.2f} mm)'

    ax.text(2, 1, total_size_txt, size=12, ha='left', va='bottom')

    ax.set_xlim(0, x0+x_total+5)
    ax.set_ylim(0, y0+y_total+5)
    ax.set_aspect(1)
    ax.axis('off')
    plt.show()

    if out_filename is None:
        (_, out_filename) = tempfile.mkstemp(suffix='.png')
        
    fig.savefig(out_filename, dpi=72)
    return out_filename


def base64_encode_file(fn):
    '''
    Assumes the file is small enough to fit in memory.  Intended for use with
    images, to embed directly in HTML.
    '''
    with open(fn, 'rb') as f:
        bstr = base64.b64encode(f.read())
    return bstr.decode('utf-8')