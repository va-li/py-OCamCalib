"""
     Hugo Vazquez email: hugo.vazquez@jakarto.com
     Copyright (C) 2022  Hugo Vazquez

     This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

     This program is distributed in the hope that it will be useful,
     but WITHOUT ANY WARRANTY; without even the implied warranty of
     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
     GNU General Public License for more details.

     You should have received a copy of the GNU General Public License along
     with this program; if not, write to the Free Software Foundation, Inc.,
     51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

import json
import pickle
from itertools import product
from pathlib import Path
from typing import Tuple, Union, Optional, List
import cv2 as cv
import numpy as np
from datetime import datetime
from tqdm import tqdm
import matplotlib.pyplot as plt
from loguru import logger
from scipy.spatial.distance import cdist

from pyocamcalib.core._utils import get_reprojection_error_all, get_reprojection_error
from pyocamcalib.core.linear_estimation import get_first_linear_estimate, get_taylor_linear
from pyocamcalib.core.optim import bundle_adjustement
from pyocamcalib.modelling.utils import get_files, generate_checkerboard_points, check_detection, transform, save_calib, \
    get_canonical_projection_model, Loader, get_incident_angle

FIG_SIZE = (12, 12)
DPI=300
class CalibrationEngine:
    def __init__(self,
                 working_dir: str,
                 chessboard_size: Tuple[int, int],
                 camera_name: str,
                 square_size: float = 1):
        """
        :param working_dir: path to folder which contains all chessboard images
        :param chessboard_size: Number of INNER corners per a chessboard (row, column)
        """
        self.incident_angles_rad_list = None
        self.reprojection_errors_list = None
        self.rms_std_list = None
        self.rms_mean_list = None
        self.rms_overall = None
        self.extrinsics_t_linear = None
        self.taylor_coefficient_linear = None
        self.working_dir = Path(working_dir)
        self.images_path = [str(e) for e in get_files(Path(working_dir))]
        self.chessboard_size = chessboard_size
        self.square_size = square_size
        self.sensor_size = cv.imread(str(self.images_path[0])).shape[:2][::-1]
        self.distortion_center = (self.sensor_size[0] / 2, self.sensor_size[1] / 2)
        self.detections = {}
        self.distortion_center_linear = None
        self.extrinsics_t = None
        self.taylor_coefficient = None
        self.stretch_matrix = None
        self.valid_pattern = None
        self.cam_name = camera_name
        self.inverse_poly = None

    def detect_corners(self, check: bool = False, window_size: Union[str, int] = "adaptive", max_height: int = 520):
        images_path = get_files(self.working_dir)
        count = 0
        world_points = generate_checkerboard_points(self.chessboard_size, self.square_size, z_axis=True)

        logger.info("Start corners extraction")

        for img_f in tqdm(images_path):
            img = cv.imread(str(img_f))
            height, width = img.shape[:2]
            ratio = width / height
            # image is downsized for faster but less accurate detection
            img_resize = cv.resize(img, (round(ratio * max_height), max_height))
            # resize ratio is stored to be able to rescale the detected corner pixel coordinates
            r_h = height / max_height
            r_w = width / (ratio * max_height)

            gray_resize = cv.cvtColor(img_resize, cv.COLOR_BGR2GRAY)
            gray = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
            for block, bias in list(product(range(20, 40, 5), range(-10, 31, 5))):

                block = (block // 2) * 2 + 1
                img_bw = cv.adaptiveThreshold(gray_resize, 255, cv.ADAPTIVE_THRESH_MEAN_C, cv.THRESH_BINARY, block,
                                              bias)
                ret, corners = cv.findChessboardCornersSB(img_bw, self.chessboard_size, flags=cv.CALIB_CB_EXHAUSTIVE)

                if not ret:
                    ret, corners = cv.findChessboardCornersSB(img_bw, self.chessboard_size, flags=0)

                if ret:
                    corners = np.squeeze(corners)
                    # rescale the detected corner coordinates to the original image size
                    corners[:, 0] *= r_w
                    corners[:, 1] *= r_h
                    
                    if window_size == "adaptive":
                        # calculate distance between all corners, returns a len(corners) x len(corners) matrix
                        pairwise_distances = cdist(corners, corners, 'euclidean')
                        
                        # keep only _one_ distance for each pair of corners, and discard distances between a corner and itself
                        # which means taking only the upper triangular part of the matrix
                        pairwise_distances = pairwise_distances[np.triu_indices(pairwise_distances.shape[0], k=1)]
                    
                        # the minimum distance between any two corners should give us a good estimate of the window size
                        distance_min = np.min(pairwise_distances)
                        
                        # then we use half the minimum distance as the window size
                        # also the window size must be an integer, so the we truncate it towards zero
                        win_size = max(int(distance_min / 2), 5)
                    else:
                        win_size = window_size
                        
                    zero_zone = (-1, -1)
                    criteria = (cv.TERM_CRITERIA_EPS + cv.TermCriteria_COUNT, 40, 0.001)
                    corners = np.expand_dims(corners, axis=0)
                    cv.cornerSubPix(gray, corners, (win_size, win_size), zero_zone, criteria)
                    
                    if check:
                        check_detection(np.squeeze(corners), img)
                    count += 1
                    self.detections[str(img_f)] = {"image_points": np.squeeze(corners)[::-1],
                                                   "world_points": np.squeeze(world_points)}
                    break
        if check:
            # Close the window created by check_detection
            cv.destroyAllWindows()

        logger.info(f"Extracted chessboard corners with success = {count}/{len(images_path)}")

    def save_detection(self, directory: str):
        with (Path(directory) / f'corner_detections_{self.cam_name}.pickle').open('wb') as f:
            pickle.dump(self.detections, f)

            logger.info(f"Detection file saved with success.")

    def load_detection(self, file_path: str):
        with open(file_path, 'rb') as f:
            self.detections = pickle.load(f)
            logger.info("Detection file loaded with success.")

    def estimate_fisheye_parameters(self, grid_size: int = 5):
        if not self.detections:
            raise ValueError('Detections is empty. You first need to detect corners in several chessboard images or '
                             'load a detection file.')

        loader = Loader("INFO:: Start first linear estimation ... ", "", 0.5).start()
        valid_pattern, d_center, min_rms, extrinsics_t, taylor_t = get_first_linear_estimate(self.detections,
                                                                                             self.sensor_size,
                                                                                             grid_size)
        
        # the linear estimation can fail, when the images are not good enough
        if valid_pattern == None or not any(valid_pattern):
            loader.stop()
            logger.error("Linear estimation failed of parameters failed. Check the chessboard detection in the supplied calibartion images!")
            raise ValueError("Linear estimation failed of parameters failed.")
        elif not all(valid_pattern):
            loader.stop()
            invalid_images = [Path(img_path).name for img_path, valid in zip(self.detections.keys(), valid_pattern) if not valid]
            logger.warning("Some chessboard patterns were deemed invalid during the linear estimation:\n"
                            f"Invalid images: {invalid_images}")

        taylor_coefficient, extrinsics_t = get_taylor_linear(self.detections, valid_pattern, extrinsics_t, d_center)
        loader.stop()
        rms_overall, _, _, _, _ = get_reprojection_error_all(self.detections, valid_pattern,
                                                       extrinsics_t, taylor_coefficient,
                                                       d_center)

        logger.info(f"Linear estimation end with success \n"
                    f"Linear RMS = {rms_overall:0.2f} \n"
                    f"Distortion Center = {d_center}\n"
                    f"Taylor_coefficient = {taylor_coefficient}\n")

        self.distortion_center_linear = d_center
        self.taylor_coefficient_linear = taylor_coefficient
        self.extrinsics_t_linear = extrinsics_t
        self.valid_pattern = valid_pattern

        loader = Loader("INFO:: Start bundle adjustment  ... ", "", 0.5).start()
        extrinsics_t_opt, stretch_matrix, d_center_opt, taylor_coefficient_opt = bundle_adjustement(self.detections,
                                                                                                    valid_pattern,
                                                                                                    extrinsics_t,
                                                                                                    d_center,
                                                                                                    taylor_coefficient)
        loader.stop()
        self.distortion_center = d_center_opt
        self.taylor_coefficient = taylor_coefficient_opt
        self.extrinsics_t = extrinsics_t_opt
        self.stretch_matrix = stretch_matrix

        rms_overall, rms_mean_list, rms_std_list, reprojection_errors_list, incident_angles_rad_list = get_reprojection_error_all(self.detections, valid_pattern,
                                                                              self.extrinsics_t,
                                                                              self.taylor_coefficient,
                                                                              self.distortion_center,
                                                                              self.stretch_matrix)
        
        logger.info(f"Bundle Adjustment end with success \n"
                    f"Optimize rms = {rms_overall:0.2f} \n"
                    f"Distortion Center = {d_center_opt}\n"
                    f"Taylor_coefficient = {taylor_coefficient_opt}\n")

        self.incident_angles_rad_list = incident_angles_rad_list
        self.reprojection_errors_list = reprojection_errors_list
        self.rms_overall = rms_overall
        self.rms_mean_list = rms_mean_list
        self.rms_std_list = rms_std_list

    def get_chessboard_points_in_camera_system(self):
        if not self.detections:
            raise ValueError(
                'Detections is empty. You first need to detect corners in several chessboard images or '
                'load a detection file.')

        if not self.extrinsics_t:
            raise ValueError('Extrinsics parameters are empty. You first need to calibrate camera.')

        world_points = generate_checkerboard_points(self.chessboard_size, self.square_size, z_axis=True)
        world_points_c = []

        for r in self.extrinsics_t:
            world_points_c.append(transform(r, world_points))

        return world_points_c
    
    def get_valid_image_paths(self) -> List[str]:
        """Return the list of valid image paths, i.e. the images that were successfully detected and a linear estimate of the rotation and translation was found.

        Returns:
            List[str]: List of valid image paths, each corresponding to the extrinsics, errors, etc with the same index in the lists.
        """
        return [img_path for img_path, valid in zip(self.detections.keys(), self.valid_pattern) if valid]

    def show_reprojection(self, save_directory: Optional[str] = None):

        if not self.detections:
            raise ValueError(
                'Detections is empty. You first need to detect corners in several chessboard images or '
                'load a detection file.')

        if self.extrinsics_t is None or self.taylor_coefficient is None:
            raise ValueError(
                'Camera parameters are empty. You first need to perform calibration or load calibration file.')

        for i, img_path in enumerate(self.get_valid_image_paths()):
            image_points = np.array(self.detections[img_path]['image_points'])
            world_points = np.array(self.detections[img_path]['world_points'])
            extrinsics = self.extrinsics_t[i]

            im = cv.imread(str(img_path))
            h, w = im.shape[:2]
            im_center = (w / 2, h / 2)

            re_mean, re_std, reprojected_image_points = get_reprojection_error(image_points, world_points,
                                                                                self.taylor_coefficient, extrinsics,
                                                                                self.distortion_center,
                                                                                self.stretch_matrix)
            ratio = w / h
            fig_size_x = 20
            fig_size_y = fig_size_x / ratio
            plt.figure(figsize=(fig_size_x, fig_size_y))
            plt.imshow(im[:, :, [2, 1, 0]])
            plt.scatter(image_points[:, 0], image_points[:, 1], marker="+", c="g", label="detected points")
            plt.scatter(reprojected_image_points[:, 0], reprojected_image_points[:, 1], marker="x", c="r",
                        label="reprojected points")
            plt.scatter(self.distortion_center[0], self.distortion_center[1], c='m', s=20,
                        label="distortion_center")
            plt.scatter(im_center[0], im_center[1], c='c', s=20, label="image center")
            plt.title(
                f"Linear estimate solution (Reprojection error $ \mu $ = {re_mean:0.2f} $\sigma$ = {re_std:0.2f}). "
                f"Distortion center = ({self.distortion_center[0]:0.2f}, {self.distortion_center[1]:0.2f})")
            plt.legend()
            
            if save_directory:
                if not (Path(save_directory) / 'reprojections').exists():
                    (Path(save_directory) / 'reprojections').mkdir(parents=False, exist_ok=True)
                else:
                    plt.savefig(Path(save_directory) / 'reprojections' / f"reprojection_{Path(img_path).stem}.png", dpi=DPI)
            
            plt.show()
                
    def show_mean_reprojection_error(self, save_directory: Optional[str] = None):

        plt.figure(figsize=FIG_SIZE)
        plt.bar(np.arange(len(self.rms_mean_list)), self.rms_mean_list, yerr=self.rms_std_list, align='center',
                alpha=0.5, ecolor='black', capsize=10, tick_label=[Path(p).name for p in self.get_valid_image_paths()])
        plt.axhline(self.rms_overall, color='g', linestyle='--', label=f"Overall RMS = {self.rms_overall:0.2f}")
        plt.xticks(rotation=90)
        plt.ylabel('Mean Error in Pixels')
        plt.xlabel("Images")
        plt.title(f'Mean Reprojection Error per Image {self.cam_name}')
        plt.legend()
        
        if save_directory:
            plt.savefig(Path(save_directory) / f"Mean_reprojection_error_{self.cam_name}.png", dpi=DPI)
        
        plt.show()
    
    def show_reporjection_error_scatter(self, save_directory: Optional[str] = None):
        """
        Show the error scatter plot of the calibration.
        :return:
        """
        if not self.detections:
            raise ValueError(
                'Detections is empty. You first need to detect corners in several chessboard images or '
                'load a detection file.')
        
        if self.extrinsics_t is None or self.taylor_coefficient is None:
            raise ValueError(
                'Camera parameters are empty. You first need to perform calibration or load calibration file.')
        
        plt.figure(figsize=FIG_SIZE)
        for i, (errors, image_path) in enumerate(zip(self.reprojection_errors_list, self.get_valid_image_paths())):
            # when the number of images is greater than 10, we change the marker style 
            marker = ['o', 'x', '+', '*'][i // 10]
            plt.scatter(errors[:, 0], errors[:, 1], marker=marker, label=Path(image_path).name)
            
        plt.xlabel("Error in x direction (pixels)")
        plt.ylabel("Error in y direction (pixels)")
        plt.title(f"Reprojection error scatter plot for {self.cam_name}")
        plt.grid()
        plt.legend()
        
        if save_directory is not None:
            plt.savefig(Path(save_directory) / f"Reprojection_error_scatter_{self.cam_name}.png", dpi=DPI)
        
        plt.show()
        
    def show_reporjection_error_by_angle(self, save_directory: Optional[str] = None):
        """
        Show the error scatter plot of the calibration.
        :return:
        """
        if not self.detections:
            raise ValueError(
                'Detections is empty. You first need to detect corners in several chessboard images or '
                'load a detection file.')
        
        if self.extrinsics_t is None or self.taylor_coefficient is None:
            raise ValueError(
                'Camera parameters are empty. You first need to perform calibration or load calibration file.')
            
        # calculate the length of each error vector (sqrt(x^2 + y^2)) and plot it against the incident angle in degrees
        
        plt.figure(figsize=FIG_SIZE)
        for i, (errors, angles, image_path) in enumerate(zip(self.reprojection_errors_list, self.incident_angles_rad_list, self.get_valid_image_paths())):
            distances = np.linalg.norm(errors, axis=1)
            # when the number of images is greater than 10, we change the marker style 
            marker = ['o', 'x', '+', '*'][i // 10]
            plt.scatter(np.degrees(angles), distances, marker=marker, label=Path(image_path).name)
            
        plt.xlabel("Incident angle (degrees)")
        plt.ylabel("Error distance (pixels)")
        plt.title(f"Reprojection error by incident angle for {self.cam_name}")
        plt.legend()
        plt.grid(True)
        
        if save_directory:
            plt.savefig(Path(save_directory) / f"Reporjection_error_by_angle_{self.cam_name}.png", dpi=DPI)
        
        plt.show()
        
    def show_3d_chessboards(self, save_directory: Optional[str] = None):
        """
        Show the 3D chessboard in camera's coordinate system.
        :return:
        """
        
        if not self.detections:
            raise ValueError(
                'Detections is empty. You first need to detect corners in several chessboard images or '
                'load a detection file.')
            
        if self.extrinsics_t is None or self.taylor_coefficient is None:
            raise ValueError(
                'Camera parameters are empty. You first need to perform calibration or load calibration file.')
        
        fig = plt.figure(figsize=FIG_SIZE)
        ax = fig.add_subplot(projection='3d')
        
        chessboard_points = self.get_chessboard_points_in_camera_system()
        valid_images = self.get_valid_image_paths()
        
        # axes_min_max will store the min and max values of any axis to set the limits of the plot
        axes_min_max = [np.inf, -np.inf]
        
        for i, (points, image_path) in enumerate(zip(chessboard_points, valid_images)):
            # find the min and max values of any axis to set the limits of the plot
            axes_min_max[0] = min(axes_min_max[0], points.min())
            axes_min_max[1] = max(axes_min_max[1], points.max())
            
            marker = ['o', 'x', '+', '*'][i // 10]
            ax.scatter(points[:, 0], points[:, 1], points[:, 2], marker=marker, label=Path(image_path).name)
        
        # set the labels and title of the plot
        ax.set_xlabel('X [meters]')
        ax.set_ylabel('Y [meters]')
        ax.set_zlabel('Z [meters]')
        ax.set_title(f"3D chessboard locations for {self.cam_name}")
        
        # set the limits of the plot to be the same for all axes
        ax.set_xlim(axes_min_max)
        ax.set_ylim(axes_min_max)
        ax.set_zlim(axes_min_max)

        plt.legend()
        
        if save_directory:
            plt.savefig(Path(save_directory) / f"3D_chessboards_{self.cam_name}.png", dpi=DPI)
        
        plt.show()
        
    def show_model_projection(self, save_directory: Optional[str] = None):
        """
        Get the projection model mapping, i.e. the radius/theta curve with radius the distance from a pixel to the
        distortion center and theta the incidence angle of ray (.wrt z axis).
        :return: radius = f(theta)
        """

        w, h = self.sensor_size
        u = np.arange(0, w, 20).astype(float)
        v = np.arange(0, h, 20).astype(float)
        u, v = np.meshgrid(u, v)
        uv_points = np.vstack((u.flatten(), v.flatten())).T

        # First transform the sensor pixel point to the ideal image pixel point ().
        uv_points -= self.distortion_center
        stretch_inv = np.linalg.inv(self.stretch_matrix)
        uv_points = uv_points @ stretch_inv.T

        rho = np.sqrt(uv_points[:, 0] ** 2 + uv_points[:, 1] ** 2)
        x = uv_points[:, 0]
        y = uv_points[:, 1]
        z = np.polyval(self.taylor_coefficient[::-1], rho)
        norm = np.sqrt(x ** 2 + y ** 2 + z ** 2)

        world_points = np.vstack((x, y, z)).T / norm[:, None]

        theta = np.arctan2(np.sqrt(world_points[:, 0] ** 2 + world_points[:, 1] ** 2), world_points[:, 2])

        theta = np.degrees(theta)
        r_calibrated = rho / np.max(rho)

        r_rect, theta_rect = get_canonical_projection_model("rectilinear", 240)
        r_equisolid, theta_equisolid = get_canonical_projection_model("equisolid", 240)
        r_equidistant, theta_equidistant = get_canonical_projection_model("equidistant", 240)
        r_stereographic, theta_stereographic = get_canonical_projection_model("stereographic", 240)

        plt.figure(figsize=FIG_SIZE)
        plt.plot(theta, r_calibrated, c='r', label=" calibrated camera")
        plt.plot(theta_rect, r_rect, c='b', label="rectilinear")
        plt.plot(theta_equisolid, r_equisolid, c='m', label="equisolid")
        plt.plot(theta_equidistant, r_equidistant, c='k', label="equidistant")
        plt.plot(theta_stereographic, r_stereographic, c='b', label="stereographic")
        plt.xlabel("Incident angle in degree")
        plt.ylabel("Radius / focal_length")
        plt.title(f"Projection model of {self.cam_name}")
        plt.ylim([0, 1])
        plt.legend()
        
        if save_directory:
            plt.savefig(Path(save_directory) / f"Model_projection_{self.cam_name}.png", dpi=DPI)
        
        plt.show()

        return r_calibrated, theta

    def save_calibration(self, directory: str):
        """
        Save calibration results in .json file
        :return: None
        """
        now = datetime.now()
        dt_string = now.strftime("%d%m%Y_%H%M%S")
        outputs = {"date": dt_string,
                   "camera_name": self.cam_name,
                   "valid": self.valid_pattern,
                   "taylor_coefficient": self.taylor_coefficient.tolist(),
                   "distortion_center": self.distortion_center,
                   "stretch_matrix": self.stretch_matrix.tolist(),
                   "inverse_poly": self.inverse_poly.tolist(),
                   "extrinsics_t": [e.tolist() for e in self.extrinsics_t],
                   "img_path": self.images_path,
                   "rms_overall": self.rms_overall,
                   "rms_mean_list": self.rms_mean_list,
                   "rms_std_list": self.rms_std_list
                   }

        with (Path(directory) / f'calibration_{self.cam_name}.json').open('w') as f:
            json.dump(outputs, f, indent=4)

    def find_poly_inv(self,
                      nb_sample: int = 100,
                      sample_ratio: float = 0.9,
                      max_degree_inverse_poly: int = 25
                      ):
        """
              Find an approximation of the inverse function. New function is much faster !
              :return:
              """
        if self.taylor_coefficient is None or self.distortion_center is None:
            raise ValueError("Fisheye parameters are empty. You first need to specify or load camera's parameters.")

        if sample_ratio < 0 or sample_ratio > 1:
            raise ValueError(f"sample_ratio have to be between 0 and 1. sample_ratio={sample_ratio} is not allow.")

        logger.info("Start searching approximation of the inverse function...")

        theta = np.linspace(0, np.pi * sample_ratio, nb_sample)
        rho = []
        for i in range(nb_sample):
            taylor_tmp = self.taylor_coefficient[::-1].copy()
            taylor_tmp[-2] -= np.tan(np.pi / 2 - theta[i])
            roots = np.roots(taylor_tmp)
            roots = roots[(roots > 0) & (np.imag(roots) == 0)]
            roots = np.array([float(np.real(e)) for e in roots])
            if roots.shape[0] == 0:
                rho.append(np.nan)
            else:
                rho.append(np.min(roots))

        rho = np.array(rho)
        max_error = float("inf")
        deg = 1

        # Repeat until the reprojection error is smaller than 0.01 pixels
        while (max_error > 0.01) & (deg < max_degree_inverse_poly):
            inv_coefficient = np.polyfit(theta, rho, deg)
            rho_inv = np.polyval(inv_coefficient, theta)
            max_error = np.max(np.abs(rho - rho_inv))
            deg += 1
        import matplotlib.pyplot as plt
        logger.info("Poly fit end with success.")
        logger.info(f"Reprojection Error : {max_error:0.4f}")
        logger.info(f"Reprojection polynomial degree: {deg}")
        logger.info(f"Inverse coefficients : {inv_coefficient}")
        self.inverse_poly = inv_coefficient
