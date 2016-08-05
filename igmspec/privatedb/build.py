""" Module to build a private DB
"""
from __future__ import print_function, absolute_import, division, unicode_literals

import numpy as np
import igmspec
import h5py
import numbers
import pdb

from igmspec import defs
from igmspec.ingest import boss, hdlls, kodiaq, ggg, sdss, hst_z2

from astropy.table import Table, vstack, Column
from astropy.coordinates import SkyCoord, match_coordinates_sky
from astropy import units as u

def grab_files(tree_root):
    """ Generate a list of FITS files within the file tree

    Parameters
    ----------
    tree_root : str
      Top level path of the tree of FITS files

    Returns
    -------
    files : list
      List of files

    """

def meta(files):

def ver01(test=False, mk_test_file=False):
    """ Build version 1.0

    Parameters
    ----------
    test : bool, optional
      Run test only
    mk_test_file : bool, optional
      Generate the test file for Travis tests?
      Writes catalog and HD-LLS dataset only

    Returns
    -------

    """
    version = 'v01'
    # HDF5 file
    if mk_test_file:
        outfil = igmspec.__path__[0]+'/tests/files/IGMspec_DB_{:s}_debug.hdf5'.format(version)
        print("Building debug file: {:s}".format(outfil))
        test = True
    else:
        outfil = igmspec.__path__[0]+'/../DB/IGMspec_DB_{:s}.hdf5'.format(version)
    hdf = h5py.File(outfil,'w')

    # Defs
    zpri = defs.z_priority()
    lenz = [len(zpi) for zpi in zpri]
    dummyf = str('#')*np.max(np.array(lenz))  # For the Table
    stypes = defs.list_of_stypes()
    lens = [len(stype) for stype in stypes]
    dummys = str('#')*np.max(np.array(lens))  # For the Table
    #cdict = defs.get_cat_dict()

    # Main DB Table  (WARNING: THIS MAY TURN INTO SQL)
    idict = dict(RA=0., DEC=0., IGM_ID=0, zem=0., sig_zem=0.,
                 flag_zem=dummyf, flag_survey=0, STYPE=dummys)
    tkeys = idict.keys()
    lst = [[idict[tkey]] for tkey in tkeys]
    maindb = Table(lst, names=tkeys)

    ''' BOSS_DR12 '''
    # Read
    boss_meta = boss.meta_for_build()
    nboss = len(boss_meta)
    # IDs
    boss_ids = np.arange(nboss,dtype=int)
    boss_meta.add_column(Column(boss_ids, name='IGM_ID'))
    # Survey flag
    flag_s = defs.survey_flag('BOSS_DR12')
    boss_meta.add_column(Column([flag_s]*nboss, name='flag_survey'))
    # Check
    assert chk_maindb_join(maindb, boss_meta)
    # Append
    maindb = vstack([maindb,boss_meta], join_type='exact')
    if mk_test_file:
        maindb = maindb[1:100]  # Eliminate dummy line
    else:
        maindb = maindb[1:]  # Eliminate dummy line
    #if not test:
    #    boss.hdf5_adddata(hdf, sdss_ids, sname)

    ''' SDSS DR7'''
    sname = 'SDSS_DR7'
    print('===============\n Doing {:s} \n===============\n'.format(sname))
    sdss_meta = sdss.meta_for_build()
    # IDs
    sdss_cut, new, sdss_ids = set_new_ids(maindb, sdss_meta)
    nnew = np.sum(new)
    # Survey flag
    flag_s = defs.survey_flag(sname)
    sdss_cut.add_column(Column([flag_s]*nnew, name='flag_survey'))
    midx = np.array(maindb['IGM_ID'][sdss_ids[~new]])
    maindb['flag_survey'][midx] += flag_s   # ASSUMES NOT SET ALREADY
    # Append
    assert chk_maindb_join(maindb, sdss_cut)
    if mk_test_file:
        sdss_cut = sdss_cut[0:100]
    maindb = vstack([maindb, sdss_cut], join_type='exact')
    # Update hf5 file
    if not test:
        sdss.hdf5_adddata(hdf, sdss_ids, sname)

    ''' KODIAQ DR1 '''
    sname = 'KODIAQ_DR1'
    print('==================\n Doing {:s} \n==================\n'.format(sname))
    kodiaq_meta = kodiaq.meta_for_build()
    # IDs
    kodiaq_cut, new, kodiaq_ids = set_new_ids(maindb, kodiaq_meta)
    nnew = np.sum(new)
    # Survey flag
    flag_s = defs.survey_flag(sname)
    kodiaq_cut.add_column(Column([flag_s]*nnew, name='flag_survey'))
    midx = np.array(maindb['IGM_ID'][kodiaq_ids[~new]])
    maindb['flag_survey'][midx] += flag_s   # ASSUMES NOT SET ALREADY
    # Append
    assert chk_maindb_join(maindb, kodiaq_cut)
    maindb = vstack([maindb,kodiaq_cut], join_type='exact')
    # Update hf5 file
    if not test:
        kodiaq.hdf5_adddata(hdf, kodiaq_ids, sname)

    ''' HD-LLS '''
    sname = 'HD-LLS_DR1'
    print('===============\n Doing {:s} \n==============\n'.format(sname))
    # Read
    hdlls_meta = hdlls.meta_for_build()
    # IDs
    hdlls_cut, new, hdlls_ids = set_new_ids(maindb, hdlls_meta)
    nnew = np.sum(new)
    # Survey flag
    flag_s = defs.survey_flag(sname)
    hdlls_cut.add_column(Column([flag_s]*nnew, name='flag_survey'))
    midx = np.array(maindb['IGM_ID'][hdlls_ids[~new]])
    maindb['flag_survey'][midx] += flag_s   # ASSUMES NOT SET ALREADY
    # Append
    assert chk_maindb_join(maindb, hdlls_cut)
    maindb = vstack([maindb,hdlls_cut], join_type='exact')
    # Update hf5 file
    if (not test) or mk_test_file:
        hdlls.hdf5_adddata(hdf, hdlls_ids, sname, mk_test_file=mk_test_file)

    ''' GGG '''
    sname = 'GGG'
    print('===============\n Doing {:s} \n==============\n'.format(sname))
    ggg_meta = ggg.meta_for_build()
    # IDs
    ggg_cut, new, ggg_ids = set_new_ids(maindb, ggg_meta)
    nnew = np.sum(new)
    # Survey flag
    flag_s = defs.survey_flag(sname)
    ggg_cut.add_column(Column([flag_s]*nnew, name='flag_survey'))
    midx = np.array(maindb['IGM_ID'][ggg_ids[~new]])
    maindb['flag_survey'][midx] += flag_s   # ASSUMES NOT SET ALREADY
    # Append
    assert chk_maindb_join(maindb, ggg_cut)
    maindb = vstack([maindb,ggg_cut], join_type='exact')
    # Update hf5 file
    if not mk_test_file:
        ggg.hdf5_adddata(hdf, ggg_ids, sname)

    # Check for duplicates
    if not chk_for_duplicates(maindb):
        raise ValueError("Failed duplicates")

    # Check for junk

    # Finish
    hdf['catalog'] = maindb
    hdf['catalog'].attrs['EPOCH'] = 2000.
    hdf['catalog'].attrs['Z_PRIORITY'] = zpri
    hdf['catalog'].attrs['VERSION'] = version
    #hdf['catalog'].attrs['CAT_DICT'] = cdict
    #hdf['catalog'].attrs['SURVEY_DICT'] = defs.get_survey_dict()
    hdf.close()
    print("Wrote {:s} DB file".format(outfil))


def ver02(test=False, mk_test_file=False, skip_copy=False):
    """ Build version 2.X

    Reads previous datasets from v1.X

    Parameters
    ----------
    test : bool, optional
      Run test only
    mk_test_file : bool, optional
      Generate the test file for Travis tests?
      Writes catalog and HD-LLS dataset only
    skip_copy : bool, optional
      Skip copying the data from v01

    Returns
    -------
    """
    # Read v1.X
    v01file = igmspec.__path__[0]+'/../DB/IGMspec_DB_v01.hdf5'
    v01file_debug = igmspec.__path__[0]+'/tests/files/IGMspec_DB_v01_debug.hdf5'
    print("Loading v01")
    v01hdf = h5py.File(v01file,'r')
    maindb = v01hdf['catalog'].value

    # Start new file
    version = 'v02'
    if mk_test_file:
        outfil = igmspec.__path__[0]+'/tests/files/IGMspec_DB_{:s}_debug.hdf5'.format(version)
        print("Building debug file: {:s}".format(outfil))
        test = True
    else:
        outfil = igmspec.__path__[0]+'/../DB/IGMspec_DB_{:s}.hdf5'.format(version)
    hdf = h5py.File(outfil,'w')

    # Copy over the old stuff
    if (not test) and (not skip_copy):
        for key in v01hdf.keys():
            if key == 'catalog':
                continue
            else:
                v01hdf.copy(key, hdf)
    if mk_test_file:
        v01hdf_debug = h5py.File(v01file_debug,'r')
        # Copy orginal
        for key in v01hdf_debug.keys():
            if key == 'catalog':
                dmaindb = v01hdf_debug[key].value
            else:
                v01hdf_debug.copy(key, hdf)
        # Add some SDSS for script test
        bsdssi = np.where(maindb['flag_survey'] == 3)[0][0:10]
        sdss_meta = v01hdf['SDSS_DR7']['meta']
        sdssi = np.in1d(maindb['IGM_ID'][bsdssi], sdss_meta['IGM_ID'])
        hdf.create_group('SDSS_DR7')
        ibool = np.array([False]*len(sdss_meta))
        ibool[sdssi] = True
        # Generate
        hdf['SDSS_DR7']['meta'] = sdss_meta[ibool]
        hdf['SDSS_DR7']['spec'] = v01hdf['SDSS_DR7']['spec'][ibool]
        # Finish
        test = True
        maindb = dmaindb

    ''' HST_z2 '''
    if not mk_test_file:
        sname = 'HST_z2'
        print('===============\n Doing {:s} \n==============\n'.format(sname))
        # Read
        hstz2_meta = hst_z2.meta_for_build()
        # IDs
        hstz2_cut, new, hstz2_ids = set_new_ids(maindb, hstz2_meta)
        nnew = np.sum(new)
        if nnew > 0:
            raise ValueError("All of these should be in SDSS")
        # Survey flag
        flag_s = defs.survey_flag(sname)
        midx = np.array(maindb['IGM_ID'][hstz2_ids[~new]])
        maindb['flag_survey'][midx] += flag_s
        # Update hf5 file
        if (not test):# or mk_test_file:
            hst_z2.hdf5_adddata(hdf, hstz2_ids, sname, mk_test_file=mk_test_file)

    # Finish
    hdf['catalog'] = maindb
    hdf['catalog'].attrs['EPOCH'] = 2000.
    zpri = v01hdf['catalog'].attrs['Z_PRIORITY']
    hdf['catalog'].attrs['Z_PRIORITY'] = zpri
    hdf['catalog'].attrs['VERSION'] = version
    #hdf['catalog'].attrs['CAT_DICT'] = cdict
    #hdf['catalog'].attrs['SURVEY_DICT'] = defs.get_survey_dict()
    hdf.close()
    print("Wrote {:s} DB file".format(outfil))
