# -*- coding: utf-8 -*-
'''
Created on Fri Aug 14 11:07:38 2020

@author: - JTM

A module to help with measurents for Ocean Optics spectrometers. 

'''

from time import sleep

import numpy as np
import pandas as pd

def adaptive_measurement(spectrometer, setting={}):
    '''
    For a given light source, use an adaptive procedure to find the integration 
    time which returns a spectrum whose maximum reported value in raw units is
    between 80-90% of the maximum intensity value for the device. Can take up
    to a maximum of ~3.5 mins for lower light levels, though this could be 
    reduced somewhat by optimising the algorithm.

    Parameters
    ----------
    spectrometer : seabreeze.spectrometers.Spectrometer
        The Ocean Optics spectrometer instance.
    setting : dict, optional
         The current setting of the light source (if known), to be included in
         the info_dict. For example {'led' : 5, 'intensity' : 3000}, or 
         {'intensities' : [0, 0, 0, 300, 4000, 200, 0, 0, 0, 0]}. 
         The default is {}.

    Returns
    -------
    oo_spectra : pd.DataFrame
        The resulting measurements from the Ocean Optics spectrometer.
    oo_info_dict : dict
        The companion info to the oo_spectra, with matching indices.

    '''
    # initial parameters
    intgtlims = spectrometer.integration_time_micros_limits
    maximum_intensity = spectrometer.max_intensity
    lower_intgt = None
    upper_intgt = None
    lower_bound = maximum_intensity * .8
    upper_bound = maximum_intensity * .9
    
    # start with 1000 micros
    intgt = 1000.0 
    max_reported = 0
    
    # keep sampling with different integration times until the maximum reported
    # value is within 80-90% of the maximum intensity value for the device
    while max_reported < lower_bound or max_reported > upper_bound:
        
        # if the current integration time is greater than the upper 
        # limit, set it too the upper limit
        if intgt >= intgtlims[1]:
            intgt = intgtlims[1]
            
        # set the spectrometer integration time
        spectrometer.integration_time_micros(intgt)
        sleep(.05)
        
        # obtain temperature measurements
        temps = spectrometer.f.temperature.temperature_get_all()
        sleep(.05)
        
        # obtain intensity measurements
        oo_counts = spectrometer.intensities()
        
        # get the maximum reported value
        max_reported = max(oo_counts)
        print('\tIntegration time: {} ms --> maximum reported value: {}'.format(
            intgt / 1000, max_reported))
        
        # if the integration time has reached the upper limit for the spectrometer,
        # exit the while loop, having obtained the final measurement
        if intgt == intgtlims[1]:
            break
        
        # if the max_reported value is less than the lower_bound and the
        # upper_ingt is not yet known, update the lower_intgt and double intgt
        # ready for the next iteration
        elif max_reported < lower_bound and upper_intgt is None:
            lower_intgt = intgt
            intgt *= 2.0
        
        # if the max_reported value is greater than the upper_bound, update
        # the upper_intgt and subtract half of the difference between 
        # upper_intgt and lower_intgt from intgt ready for the next iteration
        elif max_reported > upper_bound:
            upper_intgt = intgt
            intgt -= (upper_intgt - lower_intgt) / 2 
            
        # if the max_reported value is less than the lower_bound and the value
        # of upper_intgt is known, update the lower_intgt and add half
        # of the difference between upper_intgt and lower_intgt to intgt ready 
        # for the next iteration
        elif max_reported < lower_bound and upper_intgt is not None:
            lower_intgt = intgt
            intgt += (upper_intgt - lower_intgt) / 2
    
    oo_info_dict = {'board_temp'       : temps[0],
                    'micro_temp'       : temps[2],
                    'integration_time' : intgt,
                    'model'            : spectrometer.model}
    oo_info_dict = {**oo_info_dict, **setting}
    
    # return the final counts and dict of sample-related info
    return oo_counts, oo_info_dict
    
def dark_measurement(spectrometer, integration_times=[1000]):
    '''
    Sample the dark spectrum with a range of integration times. Do this for a 
    range of temperatures to characterise the relationship between temperature
    and integration time.

    '''
    wls = spectrometer.wavelengths()
    data = pd.DataFrame()
    for intgt in integration_times:
        spectrometer.integration_time_micros(intgt)
        sleep(.05)
        temps = spectrometer.f.temperature.temperature_get_all()
        sleep(.05)
        board_temp = np.round(temps[0], decimals=2)
        micro_temp = np.round(temps[2], decimals=2)
        print('Board temp: {}, integration time: {}'.format(board_temp, intgt))
        intensities = pd.DataFrame(spectrometer.intensities())
        intensities.rename(columns={0:'dark_counts'}, inplace=True)
        data = pd.concat([data, intensities])
        
    midx = pd.MultiIndex.from_product(
        [[board_temp], [micro_temp], integration_times, wls],
        names=['board_temp', 'micro_temp', 'integration_time', 'wavelengths'])
    data.index = midx
    
    return data

def predict_dark_spds(spectra_info, darkcal_file):
    '''
    Predict the dark spectra from the temperature and integration times of a
    set of measurements. These must be subtracted from measured pixel counts 
    during the unit-calibration process.

    Parameters
    ----------
    spectra_info : pd.DataFrame
        The info dataframe containing the 'board_temp' and 'integration_time'
        variables.
    calfile : string
        Path to the calibration file. This is currenly generated in MATLAB. 

    Returns
    -------
    pd.DataFrame
        The predicted dark spectra.

    '''
    c = pd.read_table(darkcal_file, skiprows=2, sep='\t', index_col=False)
    dark_spds = []
    for idx, row in spectra_info.iterrows():
        x  = spectra_info.loc[idx, 'board_temp']
        y  = spectra_info.loc[idx, 'integration_time']
        dark_spec = []
        for i in range(0, c.shape[0]):
            p00 = c.loc[i, 'p00']
            p10 = c.loc[i, 'p10']
            p01 = c.loc[i, 'p01']
            p20 = c.loc[i, 'p20']
            p11 = c.loc[i, 'p11']
            p30 = c.loc[i, 'p30']
            p21 = c.loc[i, 'p21']
            
            dark_spec.append(p00 + p10*x + p01*y + p20*x*x + p11*x*y + p30*x*x*x + p21*x*x*y)

        dark_spds.append(dark_spec)
        
    return pd.DataFrame(dark_spds)