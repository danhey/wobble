import numpy as np
import h5py
import pdb
import matplotlib.pyplot as plt
from itertools import compress

from .utils import fit_continuum

REQUIRED_3D = ['xs', 'ys', 'ivars'] # R-order lists of (N-epoch, M-pixel) arrays
REQUIRED_1D = ['bervs', 'airms'] # N-epoch arrays
OPTIONAL_1D = ['pipeline_rvs', 'pipeline_sigmas', 'dates', 'drifts', 'filelist'] # N-epoch arrays
                    # optional attributes always exist in Spectra() but may be filled with placeholders.
                    # they do not need to exist at all in an individual Spectrum().

class Spectra(object):
    """
    The spectra object: contains a block of time-series spectra 
    and associated data. 
    Includes all orders and epochs. 
    Can be loaded from an HDF5 file using the `filename` keyword, 
    or initialized as an empty dataset and built by appending
    `wobble.Spectrum` objects.
    
    Parameters
    ----------
    filename : `str` (optional)
        Name of HDF5 file storing the data.
    
    Attributes
    ----------
    N : `int`
        Number of epochs.
    R : `int`
        Number of echelle orders.
    xs : `list`
        R-order list of (N-epoch, M-pixel) arrays. May be wavelength or ln(wavelength).    
    ys : `list`
        R-order list of (N-epoch, M-pixel) arrays. May be continuum-normalized flux or ln(flux).    
    ivars : `list`
        R-order list of (N-epoch, M-pixel) arrays corresponding to inverse variances for `ys`.
    bervs : `np.ndarray`
        N-epoch array of Barycentric Earth Radial Velocity (m/s).
    airms : `np.ndarray`
        N-epoch array of observation airmasses.
    pipeline_rvs : `np.ndarray`, optional
        Optional N-epoch array of expected RVs.
    pipeline_sigs : `np.ndarray`, optional
        Optional N-epoch array of uncertainties on `pipeline_rvs`.    
    dates : `np.ndarray`, optional
        Optional N-epoch array of observation dates.
    drifts : `np.ndarray`, optional
        Optional N-epoch array of instrumental drifts.
    filelist : `np.ndarray`, optional
        Optional N-epoch array of file locations for each observation.
    """
    def __init__(self, filename=None):
        self.empty = True
        for attr in REQUIRED_3D:
            setattr(self, attr, [])
        for attr in np.append(REQUIRED_1D, OPTIONAL_1D):
            setattr(self, attr, np.array([]))
        self.N = 0 # number of epochs
        self.R = 0 # number of echelle orders
        
        if filename is not None:
            self.read(filename)
            
    def append(self, sp):
        """Append a spectrum.
        
        Parameters
        ----------
        sp : `wobble.Spectrum`
            The spectrum to be appended.
        """
        if self.empty:
            self.R = sp.R
            for attr in REQUIRED_3D:
                setattr(self, attr, getattr(sp, attr))
        else:
            assert self.R == sp.R, "Echelle orders do not match." 
            for attr in REQUIRED_3D:           
                old = getattr(self, attr)
                new = getattr(sp, attr)
                setattr(self, attr, [np.vstack([old[r], new[r]]) for r in range(self.R)])
            
        for attr in REQUIRED_1D:
            try:
                new = getattr(sp,attr)
            except: # fail with warning
                new = 1.
                print('WARNING: {0} missing; resulting solutions may be non-optimal.'.format(attr))
            setattr(self, attr, np.append(getattr(self,attr), new))
        for attr in OPTIONAL_1D:
            try:
                new = getattr(sp,attr)
            except: # fail silently
                new = 0.
            setattr(self, attr, np.append(getattr(self,attr), new))            
        self.N += 1
        self.empty = False
        
    def pop(self, i):
        """Remove and return spectrum at index i.
        
        Parameters
        ----------
        i : `int`
            The index of the spectrum to be removed.
        
        Returns
        -------
        sp : `wobble.Spectrum`
            The removed spectrum.
        """
        assert 0 <= i < self.N, "ERROR: invalid index."
        sp = Spectrum()
        sp.R = self.R
        for attr in REQUIRED_3D:
            epoch_to_split = [r[i] for r in getattr(self, attr)]
            epochs_to_keep = [np.delete(r, i, axis=0) for r in getattr(self, attr)]
            setattr(sp, attr, epoch_to_split)
            setattr(self, attr, epochs_to_keep)
        for attr in np.append(REQUIRED_1D, OPTIONAL_1D):
            all_epochs = getattr(self, attr)
            setattr(sp, attr, all_epochs[i])
            setattr(self, attr, np.delete(all_epochs, i))
        self.N -= 1
        return sp
            
       
    def read(self, filename, orders=None, epochs=None):
        """Read from file.
        
        Parameters
        ----------
        filename : `str`
            The filename (including path).
        
        orders : `list` or `None` (default `None`)
            List of echelle order indices to read. If `None`, read all.
        
        epochs : `list` or `None` (default `None`)
            List of observation epoch indices to read. If `None`, read all.
        """
        if not self.empty:
            print("WARNING: overwriting existing contents.")
        # TODO: add asserts to check data are finite, no NaNs, non-negative ivars, etc
        with h5py.File(filename) as f:
            if orders is None:
                orders = np.arange(len(f['data']))
            self.orders = orders
            if epochs is None:
                self.N = len(f['dates']) # all epochs
                self.epochs = np.arange(self.N)
            else:
                self.epochs = epochs
                self.N = len(epochs)
                for e in epochs:
                    assert (e >= 0) & (e < len(f['dates'])), \
                        "epoch #{0} is not in datafile {1}".format(e, self.origin_file)
            self.ys = [f['data'][i][self.epochs,:] for i in orders]
            self.xs = [f['xs'][i][self.epochs,:] for i in orders]
            self.ivars = [f['ivars'][i][self.epochs,:] for i in orders]
            for attr in np.append(REQUIRED_1D, OPTIONAL_1D):
                if not f[attr].dtype.type is np.bytes_:
                    setattr(self, attr, np.copy(f[attr])[self.epochs])
                else:
                    strings = [a.decode('utf8') for a in np.copy(f[attr])[self.epochs]]
                    setattr(self, attr, strings)
            self.R = len(orders) # number of orders
        self.empty = False
        
    def write(self, filename):
        """Write the currently loaded object to file.
    
        Parameters
        ----------
        filename : `str`
            The filename (including path).
        """
        with h5py.File(filename, 'w') as f:
            dset = f.create_dataset('data', data=self.ys)
            dset = f.create_dataset('ivars', data=self.ivars)
            dset = f.create_dataset('xs', data=self.xs)
            for attr in np.append(REQUIRED_1D, OPTIONAL_1D):
                if not getattr(self, attr).dtype.type is np.str_:
                    dset = f.create_dataset(attr, data=getattr(self, attr))
                else:
                    strings = [a.encode('utf8') for a in getattr(self, attr)] # h5py workaround
                    dset = f.create_dataset('filelist', data=strings)    
                    
    def drop_bad_orders(self, min_snr=5):
        try: 
            orders = np.asarray(self.orders)
        except:
            orders = np.arange(self.R)
        snrs_by_order = [np.sqrt(np.nanmean(i)) for i in self.ivars]
        orders_to_cut = np.array(snrs_by_order) < min_snr
        if np.sum(orders_to_cut) > 0:
            print("Data: Dropping orders {0} because they have average SNR < {1:.0f}".format(orders[orders_to_cut], min_snr))
            orders = orders[~orders_to_cut]
            for attr in REQUIRED_3D:
                old = getattr(self, attr)
                setattr(self, attr, list(compress(old, ~orders_to_cut)))
            self.orders = orders
            self.R = len(orders)
        if self.R == 0:
            print("All orders failed the quality cuts with min_snr={0:.0f}.".format(min_snr))
            
    def drop_bad_epochs(self, min_snr=5):
        try:
            epochs = np.asarray(self.epochs)
        except:
            epochs = np.arange(self.N)
        snrs_by_epoch = np.sqrt(np.nanmean(self.ivars, axis=(0,2)))
        epochs_to_cut = snrs_by_epoch < min_snr
        if np.sum(epochs_to_cut) > 0:
            print("Data: Dropping epochs {0} because they have average SNR < {1:.0f}".format(epochs[epochs_to_cut], min_snr))
            epochs = epochs[~epochs_to_cut]
            for attr in REQUIRED_3D:
                old = getattr(self, attr)
                setattr(self, attr, [o[~epochs_to_cut] for o in old]) # might fail if self.N = 1
            for attr in np.append(REQUIRED_1D, OPTIONAL_1D):
                setattr(self, attr, getattr(self,attr)[~epochs_to_cut])
            self.epochs = epochs
            self.N = len(epochs)
        if self.N == 0:
            print("All epochs failed the quality cuts with min_snr={0:.0f}.".format(min_snr))
            return        
        
class Spectrum(object):
    """
    An individual spectrum, including all orders at one
    epoch. Can be initialized by passing data as function 
    arguments or by calling a method to read from a 
    known file format.
    
    Parameters
    ----------
    xs : list of numpy arrays
        A list of wavelengths or log(waves), one entry 
        per echelle order.
    ys : list of numpy arrays
        A list of fluxes or log(fluxes), one entry per 
        echelle order. Must be the same shape as 
        `ys`.
    ivars : list of numpy arrays
        A list of inverse variance estimates
        for `ys`.
    """
    def __init__(self, *arg, **kwarg):
        self.empty = True # flag indicating object contains no data
        if len(arg) > 0:
            self.from_args(*arg, **kwarg) 
            
    def from_args(self, xs, ys, ivars, **kwarg):
        if not self.empty:
            print("WARNING: overwriting existing contents.")
        self.R = len(xs) # number of echelle orders
        self.filelist = 'args'
        self.xs = xs
        self.ys = ys
        self.ivars = ivars
        for key, value in kwarg.items():
            setattr(self, key, value)
        self.empty = False           
        
    def from_HARPS(self, filename, process=True):
        """Takes a HARPS CCF file; reads metadata and associated spectrum + wavelength files."""
        if not self.empty:
            print("WARNING: overwriting existing contents.")
        self.R = 72
        self.filelist = filename
        with fits.open(filename) as sp: # load up metadata
            self.pipeline_rvs = sp[0].header['HIERARCH ESO DRS CCF RVC'] * 1.e3 # m/s
            self.pipeline_sigmas = sp[0].header['HIERARCH ESO DRS CCF NOISE'] * 1.e3 # m/s
            self.drifts = sp[0].header['HIERARCH ESO DRS DRIFT SPE RV']
            self.dates = sp[0].header['HIERARCH ESO DRS BJD']        
            self.bervs = sp[0].header['HIERARCH ESO DRS BERV'] * 1.e3 # m/s
            self.airms = sp[0].header['HIERARCH ESO TEL AIRM START'] 
            self.pipeline_rvs -= self.bervs # move pipeline rvs back to observatory rest frame
            self.pipeline_rvs -= np.mean(self.pipeline_rvs) # just for plotting convenience
        spec_file = str.replace(filename, 'ccf_G2', 'e2ds') 
        spec_file = str.replace(spec_file, 'ccf_M2', 'e2ds') 
        spec_file = str.replace(spec_file, 'ccf_K5', 'e2ds')
        snrs = np.arange(self.R, dtype=np.float)
        with fits.open(spec_file) as sp:
            spec = sp[0].data
            for i in np.nditer(snrs, op_flags=['readwrite']):
                i[...] = sp[0].header['HIERARCH ESO DRS SPE EXT SN{0}'.format(str(int(i)))]
            wave_file = sp[0].header['HIERARCH ESO DRS CAL TH FILE']
        path = spec_file[0:str.rfind(spec_file,'/')+1]
        with fits.open(path+wave_file) as ww:
            wave = ww[0].data
        for r in range(self.R): # populate lists
            self.xs = [wave[r] for r in range(self.R)]
            self.ys = [spec[r] for r in range(self.R)]
            self.ivars = [snrs[r]**2/spec[r]/np.nanmean(spec[r,:]) for r in range(self.R)] # scaling hack
        self.empty = False         
        if process:
            self.mask_low_pixels()
            #self.trim_bad_edges()  
            self.transform_log()  
            self.continuum_normalize()
            self.mask_high_pixels()
                  
        
    def from_HARPSN(self, filename, process=True):
        if not self.empty:
            print("WARNING: overwriting existing contents.")
        self.R = 69
        self.filelist = filename
        with fits.open(filename) as sp: # load up metadata
            self.pipeline_rvs = sp[0].header['HIERARCH TNG DRS CCF RVC'] * 1.e3 # m/s
            self.pipeline_sigmas = sp[0].header['HIERARCH TNG DRS CCF NOISE'] * 1.e3 # m/s
            self.drifts = sp[0].header['HIERARCH TNG DRS DRIFT RV USED']
            self.dates = sp[0].header['HIERARCH TNG DRS BJD']        
            self.bervs = sp[0].header['HIERARCH TNG DRS BERV'] * 1.e3 # m/s
            self.airms = sp[0].header['AIRMASS'] 
            self.pipeline_rvs -= self.bervs # move pipeline rvs back to observatory rest frame
            self.pipeline_rvs -= np.mean(self.pipeline_rvs) # just for plotting convenience
        spec_file = str.replace(filename, 'ccf_G2', 'e2ds') 
        spec_file = str.replace(spec_file, 'ccf_M2', 'e2ds') 
        spec_file = str.replace(spec_file, 'ccf_K5', 'e2ds')
        snrs = np.arange(self.R, dtype=np.float)
        with fits.open(spec_file) as sp:
            spec = sp[0].data
            for i in np.nditer(snrs, op_flags=['readwrite']):
                i[...] = sp[0].header['HIERARCH TNG DRS SPE EXT SN{0}'.format(str(int(i)))]
            wave_file = sp[0].header['HIERARCH TNG DRS CAL TH FILE']
        path = spec_file[0:str.rfind(spec_file,'/')+1]
        with fits.open(path+wave_file) as ww:
            wave = ww[0].data
        for r in range(self.R): # populate lists
            self.xs = [wave[r] for r in range(self.R)]
            self.ys = [spec[r] for r in range(self.R)]
            self.ivars = [snrs[r]**2/spec[r]/np.nanmean(spec[r,:]) for r in range(self.R)] # scaling hack
        self.empty = False  
        if process:
            self.mask_low_pixels()
            #self.trim_bad_edges()   
            self.transform_log()  
            self.continuum_normalize()
            self.mask_high_pixels()
             
        
    def continuum_normalize(self, plot_continuum=False, plot_dir='../results/', **kwargs):
        """Continuum-normalize all orders using a polynomial fit. Takes kwargs of utils.fit_continuum"""
        for r in range(self.R):
            try:
                fit = fit_continuum(self.xs[r], self.ys[r], self.ivars[r], **kwargs)
            except:
                print("WARNING: Data: order {0} could not be continuum normalized. Setting to zero.".format(r))
                self.ys[r] = np.zeros_like(self.ys[r])
                self.ivars[r] = np.zeros_like(self.ivars[r])
                continue
            if plot_continuum:
                fig, ax = plt.subplots(1, 1, figsize=(8,5))
                ax.scatter(self.xs[r], self.ys[r], marker=".", alpha=0.5, c='k', s=40)
                mask = self.ivars[r] <= 1.e-8
                ax.scatter(self.xs[r][mask], self.ys[r][mask], marker=".", alpha=1., c='white', s=20)                        
                ax.plot(self.xs[r], fit)
                fig.savefig(plot_dir+'continuum_o{0}.png'.format(r))
                plt.close(fig)
            self.ys[r] -= fit
            
    def mask_low_pixels(self, min_flux = 1., padding = 2):
        """Set ivars to zero for pixels that fall below some minimum value (e.g. negative flux)."""
        for r in range(self.R):
            bad = np.logical_or(self.ys[r] < min_flux, np.isnan(self.ys[r]))
            self.ys[r][bad] = min_flux
            for pad in range(padding): # mask out neighbors of low pixels
                bad = np.logical_or(bad, np.roll(bad, pad+1))
                bad = np.logical_or(bad, np.roll(bad, -pad-1))
            self.ivars[r][bad] = 0.
            
    def mask_high_pixels(self, max_flux = 2., padding = 2):
        """Set ivars to zero for pixels that fall above some maximum value (e.g. cosmic rays)."""
        for r in range(self.R):
            bad = self.ys[r] > max_flux
            self.ys[r][bad] = 1.
            for pad in range(padding): # mask out neighbors of high pixels
                bad = np.logical_or(bad, np.roll(bad, padding+1))
                bad = np.logical_or(bad, np.roll(bad, -padding-1))
            self.ivars[r][bad] = 0.
            
    def trim_bad_edges(self, window_width = 128, min_snr = 5.):
        """
        Find edge regions that contain no information and set ivars there to zero.
        
        Parameters
        ----------
        window_width : `int`
            number of pixels to average over for local SNR            
        min_snr : `float`
            SNR threshold below which we discard the data
        """
        # TODO: speed this up!!
        for r in range(self.R):
            n_pix = len(self.xs[r])
            for window_start in range(n_pix - window_width):
                mean_snr = np.sqrt(np.nanmean(self.ivars[r][window_start:window_start+window_width]))
                if mean_snr > min_snr:
                    self.ivars[r][:window_start] = 0. # trim everything to left of window
                    break
            for window_start in reversed(range(n_pix - window_width)):
                mean_snr = np.sqrt(np.nanmean(self.ivars[r][window_start:window_start+window_width]))
                if mean_snr > min_snr:
                    self.ivars[r][window_start+window_width:] = 0. # trim everything to right of window
                    break
                
    def transform_log(self, xs=True, ys=True):
        """Transform xs and/or ys attributes to log-space."""
        if xs:
            self.xs = [np.log(x) for x in self.xs]
        if ys:
            self.ivars = [self.ys[i]**2 * self.ivars[i] for i in range(self.R)]
            self.ys = [np.log(y) for y in self.ys]        
        
        