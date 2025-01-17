# Occupancy Grid Mapping Counting Sensor Model Class


import numpy as np
from scipy.spatial import KDTree
from tqdm import tqdm
from utils import cart2pol, wrapToPI


# Occupancy Grid Mapping Class
class ogm_continuous_CSM:

    def __init__(self):
        # map dimensions
        self.range_x = [-15, 20]
        self.range_y = [-25, 10]

        # senesor parameters
        self.z_max = 30     # max range in meters
        self.n_beams = 133  # number of beams, we set it to 133 because not all measurements in the dataset contains 180 beams 

        # grid map parameters
        self.grid_size = 0.135                  # adjust this for task 2.B
        self.nn = 16                            # number of nearest neighbor search

        # map structure
        self.map = {}   # map
        self.pose = {}  # pose data
        self.scan = []  # laser scan data
        self.m_i = {}   # cell i

        # continuous kernel parameter
        self.l = 0.2      # kernel parameter
        self.sigma = 0.1  # kernel parameter

        # -----------------------------------------------
        # To Do: 
        # prior initialization
        # Initialize prior, prior_alpha
        # -----------------------------------------------
        self.prior = 0            # prior for setting up mean and variance
        self.prior_alpha = 1e-10  # a small, uninformative prior for setting up alpha

    def construct_map(self, pose, scan):
        # class constructor
        # construct map points, i.e., grid centroids
        x = np.arange(self.range_x[0], self.range_x[1]+self.grid_size, self.grid_size)
        y = np.arange(self.range_y[0], self.range_y[1]+self.grid_size, self.grid_size)
        X, Y = np.meshgrid(x, y)
        t = np.hstack((X.reshape(-1, 1), Y.reshape(-1, 1)))

        # a simple KDTree data structure for map coordinates
        self.map['occMap'] = KDTree(t)
        self.map['size'] = t.shape[0]

        # set robot pose and laser scan data
        self.pose['x'] = pose['x'][0][0]
        self.pose['y'] = pose['y'][0][0]
        self.pose['h'] = pose['h'][0][0]
        self.pose['mdl'] = KDTree(np.hstack((self.pose['x'], self.pose['y'])))
        self.scan = scan

        # -----------------------------------------------
        # To Do: 
        # Initialization map parameters such as map['mean'], map['variance'], map['alpha'], map['beta']
        # -----------------------------------------------
        self.map['mean'] = self.prior * np.ones([t.shape[0], 1])
        self.map['variance'] = self.prior * np.ones([t.shape[0], 1])
        self.map['alpha'] = self.prior_alpha * np.ones([t.shape[0], 1])
        self.map['beta'] = self.prior_alpha * np.ones([t.shape[0], 1])


    def is_in_perceptual_field(self, m, p):
        # check if the map cell m is within the perception field of the
        # robot located at pose p
        inside = False
        d = m - p[0:2].reshape(-1)
        self.m_i['range'] = np.sqrt(np.sum(np.power(d, 2)))
        self.m_i['phi'] = wrapToPI(np.arctan2(d[1], d[0]) - p[2])
        # check if the range is within the feasible interval
        if (0 < self.m_i['range']) and (self.m_i['range'] < self.z_max):
            # here sensor covers -pi to pi
            if (-np.pi < self.m_i['phi']) and (self.m_i['phi'] < np.pi):
                inside = True
        return inside


    def continuous_CSM(self, z, i, k):
        bearing_diff = []
        # find the nearest beam
        bearing_diff = np.abs(wrapToPI(z[:, 1] - self.m_i['phi']))
        # idx = np.nanargmin(bearing_diff)
        indexes = np.argpartition(bearing_diff, 1)
        for idx in indexes[:1]:
            global_x = self.pose['x'][k][0] + z[idx,0] * np.cos(z[idx,1] + self.pose['h'][k][0])
            global_y = self.pose['y'][k][0] + z[idx,0] * np.sin(z[idx,1] + self.pose['h'][k][0])

            # -----------------------------------------------
            # To Do: 
            # implement the continuous counting sensor model, update 
            # obj.map.alpha and obj.map.beta
            #
            # Hint: use distance and obj.l to determine occupied or free.
            # There might be multiple ways to update obj.map.beta. 
            # One way is to segment the measurement into several range 
            # values and update obj.map.beta if the distance is smaller 
            # than obj.l  
            # -----------------------------------------------
            # update end point -> occupied
            d = np.linalg.norm(self.map['occMap'].data[i, :] - [global_x, global_y])
            if d < self.l:
                kernel = self.sigma*(1/3*(2+np.cos(2*np.pi*d/self.l)*(1-d/self.l)+1/(2*np.pi)*np.sin(2*np.pi*d/self.l)))
                self.map['alpha'][i] = self.map['alpha'][i] + kernel
            else:
                # update free space
                d_o_m = np.linalg.norm(self.map['occMap'].data[i, :] - [self.pose['x'][k][0], self.pose['y'][k][0]]) # distance between robot pose and the cell
                for r in np.arange(d_o_m-self.l, min(z[idx,0], d_o_m+self.l), self.l*2/3):
                    global_x = self.pose['x'][k][0] + r * np.cos(z[idx,1] + self.pose['h'][k][0])
                    global_y = self.pose['y'][k][0] + r * np.sin(z[idx,1] + self.pose['h'][k][0])
                    dist = np.linalg.norm(self.map['occMap'].data[i,:] - [global_x, global_y])
                    if dist < self.l:
                        kernel = self.sigma*(1/3*(2+np.cos(2*np.pi*dist/self.l)*(1-dist/self.l)+1/(2*np.pi)*np.sin(2*np.pi*dist/self.l)))
                        self.map['beta'][i] = self.map['beta'][i] + kernel


    def build_ogm(self):
        # build occupancy grid map using the binary Bayes filter.
        # We first loop over all map cells, then for each cell, we find
        # N nearest neighbor poses to build the map. Note that this is
        # more efficient than looping over all poses and all map cells
        # for each pose which should be the case in online (incremental)
        # data processing.
        for i in tqdm(range(self.map['size'])):
            m = self.map['occMap'].data[i, :]
            _, idxs = self.pose['mdl'].query(m, self.nn)
            if len(idxs):
                for k in idxs:
                    # pose k
                    pose_k = np.array([self.pose['x'][k], self.pose['y'][k], self.pose['h'][k]])
                    if self.is_in_perceptual_field(m, pose_k):
                        # laser scan at kth state; convert from cartesian to
                        # polar coordinates
                        z = cart2pol(self.scan[k][0][0, :], self.scan[k][0][1, :])
                        # -----------------------------------------------
                        # To Do: 
                        # update the sensor model in cell i
                        # -----------------------------------------------
                        self.continuous_CSM(z, i, k)

            # -----------------------------------------------
            # To Do: 
            # update mean and variance for each cell i
            # -----------------------------------------------
            self.map['mean'][i] = self.map['alpha'][i] / (self.map['alpha'][i] + self.map['beta'][i])
            self.map['variance'][i] = (self.map['alpha'][i] * self.map['beta'][i]) / \
                ((self.map['alpha'][i] + self.map['beta'][i])**2 * (self.map['alpha'][i] + self.map['beta'][i] + 1))
