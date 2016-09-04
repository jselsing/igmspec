""" Module to ingest SDSS III (aka BOSS) data products
"""
from __future__ import print_function, absolute_import, division, unicode_literals


import numpy as np
import os, json
import pdb
import datetime

from astropy.table import Table, Column, vstack
from astropy.time import Time
from astropy.io import fits
from astropy.coordinates import SkyCoord, match_coordinates_sky
from astropy import units as u

from linetools import utils as ltu
from linetools.spectra import io as lsio

from igmspec.ingest import utils as iiu


def grab_meta():
    """ Grab BOSS meta Table
    Returns
    -------

    """

    #http://www.sdss.org/dr12/algorithms/boss-dr12-quasar-catalog/
    boss_dr12 = Table.read(os.getenv('RAW_IGMSPEC')+'/BOSS/DR12Q.fits.gz')
    boss_dr12['CAT'] = ['DR12Q']*len(boss_dr12)
    #
    boss_sup = Table.read(os.getenv('RAW_IGMSPEC')+'/BOSS/DR12Q_sup.fits.gz')
    boss_sup['CAT'] = ['SUPGD']*len(boss_sup)
    boss_supbad = Table.read(os.getenv('RAW_IGMSPEC')+'/BOSS/DR12Q_supbad.fits.gz')
    boss_supbad['CAT'] = ['SUPBD']*len(boss_supbad)
    # Collate
    boss_meta = vstack([boss_dr12, boss_sup, boss_supbad], join_type='outer')
    #
    nboss = len(boss_meta)
    # DATE-OBS
    t = Time(list(boss_meta['MJD'].data), format='mjd', out_subfmt='date')  # Fixes to YYYY-MM-DD
    boss_meta.add_column(Column(t.iso, name='DATE-OBS'))
    # Add columns
    boss_meta.add_column(Column(['BOSS']*nboss, name='INSTR'))
    boss_meta.add_column(Column(['BOTH']*nboss, name='GRATING'))
    #http://www.sdss.org/instruments/boss_spectrograph/
    boss_meta.add_column(Column([2100.]*nboss, name='R'))  # RESOLUTION
    boss_meta.add_column(Column(['SDSS 2.5-M']*nboss, name='TELESCOPE'))
    # Redshift logic
    boss_meta['zem'] = boss_meta['Z_PCA']
    boss_meta['sig_zem'] = boss_meta['ERR_ZPCA']
    boss_meta['flag_zem'] = [str('BOSS_PCA ')]*nboss
    # Fix bad redshifts
    bad_pca = boss_meta['Z_PCA'] < 0.
    boss_meta['zem'][bad_pca] = boss_meta['Z_PIPE'][bad_pca]
    boss_meta['sig_zem'][bad_pca] = boss_meta['ERR_ZPIPE'][bad_pca]
    boss_meta['flag_zem'][bad_pca] = str('BOSS_PIPE')
    #
    return boss_meta


def meta_for_build():
    """ Load the meta info
    DR12 quasars : https://data.sdss.org/datamodel/files/BOSS_QSO/DR12Q/DR12Q.html

    Returns
    -------

    """
    from igmspec.build_db import chk_for_duplicates
    boss_meta = grab_meta()
    # Cut down to unique
    c_main = SkyCoord(ra=boss_meta['RA'], dec=boss_meta['DEC'], unit='deg')
    idx, d2d, d3d = match_coordinates_sky(c_main, c_main, nthneighbor=2)
    dups = np.where(d2d < 2*u.arcsec)[0]
    flgs = np.array([True]*len(boss_meta))
    #
    for ii in dups:
        if boss_meta[ii]['CAT'] == 'SUPBD':
            flgs[ii] = False
    boss_meta = boss_meta[flgs]
    if not chk_for_duplicates(boss_meta):
        raise ValueError("DUPLICATES IN BOSS")
    #
    meta = Table()
    for key in ['RA', 'DEC', 'zem', 'sig_zem', 'flag_zem']:
        meta[key] = boss_meta[key]
    meta['STYPE'] = [str('QSO')]*len(meta)
    # Return
    return meta


def get_specfil(row, KG=False, hiz=False):
    """Grab the BOSS file name + path
    KG : bool, optional
      Grab MFR continuum generated by KG
    """
    pnm = '{0:04d}'.format(row['PLATE'])
    fnm = '{0:04d}'.format(row['FIBERID'])
    mjd = str(row['MJD'])
    # KG?
    if KG:
        path = os.getenv('RAW_IGMSPEC')+'/BOSS/BOSSLyaDR12_spectra_v1.0/{:s}/'.format(pnm)
        specfil = path+'speclya-{:04d}-{:d}-{:04d}.fits.gz'.format(row['PLATE'], row['MJD'], row['FIBERID'])
        return specfil

    # Generate file name (DR4 is different)
    path = os.getenv('RAW_IGMSPEC')+'/BOSS/'
    #
    if hiz:
        path += 'hiz/'
    elif row['CAT'] == 'SUPGD':
        path += 'Sup12/'
    elif row['CAT'] == 'SUPBD':
        path += 'SupBad/'
        #specfil = path+'spec-{:04d}-{:d}-{:04d}.fits.gz'.format(row['PLATE'], row['MJD'], row['FIBERID'])
    elif row['CAT'] == 'DR12Q':
        path += 'DR12Q/'
    else:
        raise ValueError("Uh oh")
    specfil = path+'spec-{:04d}-{:d}-{:04d}.fits.gz'.format(row['PLATE'], row['MJD'], row['FIBERID'])
    # Finish
    return specfil


def hdf5_adddata(hdf, IDs, sname, debug=False, chk_meta_only=False, boss_hdf=None, **kwargs):
    """ Add BOSS data to the DB

    Parameters
    ----------
    hdf : hdf5 pointer
    IDs : ndarray
      int array of IGM_ID values in mainDB
    sname : str
      Survey name
    chk_meta_only : bool, optional
      Only check meta file;  will not write
    boss_hdf : str, optional


    Returns
    -------

    """
    # Add Survey
    print("Adding {:s} survey to DB".format(sname))
    if boss_hdf is not None:
        print("Using previously generated {:s} dataset...".format(sname))
        boss_hdf.copy(sname, hdf)
        return
    boss_grp = hdf.create_group(sname)
    # Load up
    meta = grab_meta()
    bmeta = meta_for_build()
    # Checks
    if sname != 'BOSS_DR12':
        raise IOError("Not expecting this survey..")
    if np.sum(IDs < 0) > 0:
        raise ValueError("Bad ID values")
    # Open Meta tables
    if len(bmeta) != len(IDs):
        raise ValueError("Wrong sized table..")

    # Generate ID array from RA/DEC
    c_cut = SkyCoord(ra=bmeta['RA'], dec=bmeta['DEC'], unit='deg')
    c_all = SkyCoord(ra=meta['RA'], dec=meta['DEC'], unit='deg')
    # Find new sources
    idx, d2d, d3d = match_coordinates_sky(c_all, c_cut, nthneighbor=1)
    if np.sum(d2d > 1.2*u.arcsec):  # There is one system offset by 1.1"
        raise ValueError("Bad matches in BOSS")
    meta_IDs = IDs[idx]
    meta.add_column(Column(meta_IDs, name='IGM_ID'))

    # Sort

    # Build spectra (and parse for meta)
    nspec = len(meta)
    max_npix = 4650  # Just needs to be large enough
    data = np.ma.empty((1,),
                       dtype=[(str('wave'), 'float64', (max_npix)),
                              (str('flux'), 'float32', (max_npix)),
                              (str('sig'),  'float32', (max_npix)),
                              (str('co'),   'float32', (max_npix)),
                              ])
    # Init
    spec_set = hdf[sname].create_dataset('spec', data=data, chunks=True,
                                         maxshape=(None,), compression='gzip')
    spec_set.resize((nspec,))
    wvminlist = []
    wvmaxlist = []
    speclist = []
    npixlist = []
    # Loop
    maxpix = 0
    for jj,row in enumerate(meta):
        full_file = get_specfil(row)
        if full_file == 'None':
            continue
        # Extract
        print("BOSS: Reading {:s}".format(full_file))
        # Generate full file
        spec = lsio.readspec(full_file)
        # npix
        npix = spec.npix
        #if row['zem'] > 4.8:
        #    pdb.set_trace()
        if npix < 10:
            full_file = get_specfil(row, hiz=True)
            spec = lsio.readspec(full_file)
            npix = spec.npix
        elif npix > max_npix:
            raise ValueError("Not enough pixels in the data... ({:d})".format(npix))
        else:
            maxpix = max(npix,maxpix)
        # Parse name
        fname = full_file.split('/')[-1]
        # Some fiddling about
        for key in ['wave','flux','sig']:
            data[key] = 0.  # Important to init (for compression too)
        data['flux'][0][:npix] = spec.flux.value
        data['sig'][0][:npix] = spec.sig.value
        data['wave'][0][:npix] = spec.wavelength.value
        # GZ Continuum
        try:
            co = spec.co.value
        except AttributeError:
            co = np.ones_like(spec.flux.value)
        # KG Continuum
        KG_file = get_specfil(row, KG=True)
        if os.path.isfile(KG_file) and (npix>1):  # Latter is for junk in GZ file.  Needs fixing
            hduKG = fits.open(KG_file)
            KGtbl = hduKG[1].data
            wvKG = 10.**KGtbl['LOGLAM']
            try:
                assert (wvKG[0]-spec.wavelength[0].value) < 1e-5
            except:
                pdb.set_trace()
            gdpix = np.where(wvKG < (1+row['zem'])*1200.)[0]
            co[gdpix] = KGtbl['CONT'][gdpix]
            #from xastropy.xutils import xdebug as xdb
            #xdb.set_trace()
            #xdb.xplot(data['wave'][0][0:npix], data['flux'][0][0:npix], co)
        data['co'][0][:npix] = co
        # Meta
        speclist.append(str(fname))
        wvminlist.append(np.min(data['wave'][0][:npix]))
        wvmaxlist.append(np.max(data['wave'][0][:npix]))
        npixlist.append(npix)
        # Only way to set the dataset correctly
        if chk_meta_only:
            continue
        spec_set[jj] = data

    #
    print("Max pix = {:d}".format(maxpix))
    # Add columns
    meta.add_column(Column(speclist, name='SPEC_FILE'))
    meta.add_column(Column(npixlist, name='NPIX'))
    meta.add_column(Column(wvminlist, name='WV_MIN'))
    meta.add_column(Column(wvmaxlist, name='WV_MAX'))
    meta.add_column(Column(np.arange(nspec,dtype=int),name='SURVEY_ID'))
    meta.add_column(Column([2000.]*len(meta), name='EPOCH'))

    # Add HDLLS meta to hdf5
    if iiu.chk_meta(meta):
        if chk_meta_only:
            pdb.set_trace()
        hdf[sname]['meta'] = meta
    else:
        pdb.set_trace()
        raise ValueError("meta file failed")
    # References
    refs = [dict(url='http://adsabs.harvard.edu/abs/2015ApJS..219...12A',
                 bib='boss_qso_dr12'),
            ]
    jrefs = ltu.jsonify(refs)
    hdf[sname]['meta'].attrs['Refs'] = json.dumps(jrefs)
    #
    return
