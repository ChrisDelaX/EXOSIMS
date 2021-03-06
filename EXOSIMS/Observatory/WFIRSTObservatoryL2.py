from EXOSIMS.Observatory.WFIRSTObservatory import WFIRSTObservatory
import astropy.units as u
from astropy.time import Time
from astropy.coordinates import SkyCoord
import numpy as np
import os, inspect
import scipy.interpolate as interpolate
try:
    import cPickle as pickle
except:
    import pickle
from scipy.io import loadmat

class WFIRSTObservatoryL2(WFIRSTObservatory):
    """ WFIRST Observatory at L2 implementation. 
    Only difference between this and the WFIRSTObservatory implementation
    is the orbit method, and carrying an internal missionStartTime value,
    which should be the same as the one in TimeKeeping (necessary due to 
    orbit method interface, which calls for absolute time).

    Orbit is stored in pickled dictionary on disk (generated by MATLAB
    code adapted from E. Kolemen (2008).  Describes approx. 6 month halo
    which is then patched for the entire mission duration).
    """

    def __init__(self, missionStart=60634., orbit_datapath=None, **specs):
        
        # Run prototype constructor __init__ 
        WFIRSTObservatory.__init__(self,**specs)
        
        # Set own missionStart value
        self.missionStart = Time(float(missionStart), format='mjd', scale='tai')
        
        # Find and load halo orbit data
        # data is in heliocentric ecliptic coords
        # time is 2\pi = 1 sideral year
        
        if orbit_datapath is None:
            classpath = os.path.split(inspect.getfile(self.__class__))[0]
            filename = 'L2_halo_orbit_six_month.p'
            orbit_datapath = os.path.join(classpath, filename)
        if not os.path.exists(orbit_datapath):
            matname = 'L2_halo_orbit_six_month.mat'
            mat_datapath = os.path.join(classpath, matname)
            if not os.path.exists(mat_datapath):
                raise Exception("Orbit data file not found.")
            else:
                halo = loadmat( mat_datapath )
                pickle.dump( halo, open(orbit_datapath, 'wb'))
        else:
            halo = pickle.load( open( orbit_datapath, "rb" ) )
        
        # unpack orbit properties
        self.orbit_period = halo['te'].flatten()[0]/(2*np.pi)*u.year
        self.L2_dist = halo['x_lpoint'][0][0]*u.AU
        self.orbit_pos = halo['state'][:,0:3]*u.AU #this is in rotating frame wrt the sun
        self.orbit_vel = halo['state'][:,3:6]*u.AU/u.year*(2*np.pi) #velocity in rotating frame
        self.orbit_pos[:,0] -= self.L2_dist #now with respect to L2, still in rotating frame
        self.orbit_time = halo['t'].flatten()/(2*np.pi)*u.year
        # create interpolant (years & AU units)
        self.orbit_interp = interpolate.interp1d(self.orbit_time.value,\
                self.orbit_pos.value.T,kind='linear')
        # create interpolant for orbital velocity (years & AU/yr units)
        self.orbit_V_interp = interpolate.interp1d(self.orbit_time.value,\
                self.orbit_vel.value.T,kind='linear')

    def orbit(self, currentTime):
        """Finds observatory orbit position vector in heliocentric equatorial frame.
        
        This method returns the WFIRST L2 Halo orbit position vector
        in the heliocentric equatorial frame.
        
        Args:
            currentTime (astropy Time array):
                Current absolute mission time in MJD
        
        Returns:
            r_sc (astropy Quantity nx3 array):
                Observatory (spacecraft) position vector in units of km
        
        """
        
        # find time from Earth equinox and interpolated position
        equinox = Time([60575.25],format='mjd')
        deltime = currentTime - equinox
        # calculating Earth position
        r_Earth = self.solarSystem_body_position(currentTime, 'Earth')
        dist_Earth = SkyCoord(r_Earth[:,0],r_Earth[:,1],r_Earth[:,2],representation='cartesian').heliocentrictrueecliptic.icrs.distance
        # weighting L2 position with Earth-Sun distance
        L2_corr_dist = np.ones(currentTime.size)*self.L2_dist * dist_Earth.to('AU').value
        # add L2 position to get current ecliptic coord
        th = 2*np.pi*np.mod(deltime.to('yr'),1.*u.yr).value
        cpos = self.orbit_interp(np.mod(deltime.to('yr'),self.orbit_period).to('year').value)
        cpos += np.vstack((np.cos(th),np.sin(th),np.zeros(th.size)))*L2_corr_dist.to('AU').value
        # finally, rotate into equatorial plane
        TDB = self.cent(currentTime)
        obe = np.array(np.radians(self.obe(TDB)),ndmin=1)
        r_sc = np.empty((obe.size,3))*u.km
        for i in range(obe.size):
            r_sc[i,:] = (np.dot(self.rot(-obe[i],1),cpos[:,i])*u.AU).to('km')
      
        assert np.all(np.isfinite(r_sc)), 'Observatory position vector r_sc has infinite value.'
        
        return r_sc.to('km')
