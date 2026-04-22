<p align="center">
  <img src="./docs/logo.png" alt="Typer">
</p>

Py-OCamCalib is a pure Python/Numpy implementation of <a href="https://rpg.ifi.uzh.ch/people_scaramuzza.html">Scaramuzzas</a> 
<a href="https://sites.google.com/site/scarabotix/ocamcalib-omnidirectional-camera-calibration-toolbox-for-matlab">OcamCalib</a> Toolbox.

📚 This work is based on: \
Scaramuzza, D., Martinelli, A. and Siegwart, R., (2006). <a href="https://rpg.ifi.uzh.ch/docs/ICVS06_scaramuzza.pdf">"A Flexible Technique for Accurate Omnidirectional Camera Calibration and Structure from Motion", Proceedings of IEEE International Conference of Vision Systems (ICVS'06), New York, January 5-7, 2006. </a>\
Urban, S.; Leitloff, J.; Hinz, S. (2015): <a href="https://www.ipf.kit.edu/downloads/Preprint_ImprovedWideAngleFisheyeAndOmnidirectionalCameraCalibration.pdf">Improved Wide-Angle, Fisheye and Omnidirectional Camera Calibration. ISPRS Journal of Photogrammetry and Remote Sensing 108, 72-79.</a>

The key features are:

* **Easy to use**: It's easy to use for the final users. Two lines in the terminal.
* **Chessboard corners detection**: Automatic chessboard corners detection and optional manual correction to prevent miss detection.
* **Calibration parameters**: Calibration parameters are saved in .json file to better portability.
* **Camera model**: Once calibration is done, the camera class is ready to use. Load the calibration file and use all the predefined mapping 
 functions (world to pixel, pixel to world, undistorted, equirectangular projection, ...) in your project.

## Installation

### Quick Start with uv (Recommended)

[`uv`](https://github.com/astral-sh/uv) is a fast Python package manager. This is the recommended way to set up the project.

```bash
# 1. Clone the repository
git clone https://github.com/jakarto3d/py-OCamCalib.git
cd py-OCamCalib

# 2. Sync dependencies (creates .venv and installs all dependencies from pyproject.toml)
uv sync

# 3. Run calibration with uv
uv run python -m pyocamcalib.script.calibration_script /path/to/chessboard/images 9 5 --camera-name mycam --square-size 35
```

**Note**: `uv sync` will automatically create a virtual environment (`.venv/`) and install all dependencies defined in `pyproject.toml`. The package itself is installed in editable mode, so you can run the calibration scripts directly with `uv run`.

### Expected Output (Successful Calibration)

When running calibration, you should see output similar to this:

```
2026-04-22 13:15:38.103 | INFO     | pyocamcalib.modelling.calibration:detect_corners:78 - Start corners extraction
100%|██████████| 30/30 [00:04<00:00,  7.32it/s]
2026-04-22 13:15:42.810 | INFO     | pyocamcalib.modelling.calibration:detect_corners:140 - Extracted chessboard corners with success = 30/30
2026-04-22 13:15:42.810 | INFO     | pyocamcalib.modelling.calibration:save_detection:146 - Detection file saved with success.
⢿ INFO:: Start first linear estimation ...  ⡿
2026-04-22 13:16:05.628 | INFO     | pyocamcalib.modelling.calibration:estimate_fisheye_parameters:180 - Linear estimation end with success 
Linear RMS = 0.30 
Distortion Center = (760.41, 422.72)
Taylor_coefficient = [273.69, 0, -0.00162, 4.15e-06, -8.22e-09]
⢿ INFO:: Start bundle adjustment  ...  ⡿
2026-04-22 13:18:08.581 | INFO     | pyocamcalib.modelling.calibration:estimate_fisheye_parameters:208 - Bundle Adjustment end with success 
Optimize rms = 0.18 
Distortion Center = (760.43, 422.55)
Taylor_coefficient = [2.74e+02, 0.0, -1.61e-03, 4.16e-06, -8.24e-09]
2026-04-22 13:18:08.590 | INFO     | pyocamcalib.modelling.calibration:find_poly_inv:544 - Poly fit end with success.
2026-04-22 13:18:08.590 | INFO     | pyocamcalib.modelling.calibration:find_poly_inv:545 - Reprojection Error : 0.0090
2026-04-22 13:18:08.590 | INFO     | pyocamcalib.modelling.calibration:find_poly_inv:546 - Reprojection polynomial degree: 16
```

**Success indicators:**
- ✅ All images detected: `Extracted chessboard corners with success = 30/30`
- ✅ Low reprojection error: `Optimize rms = 0.18` (good calibration is typically < 0.5 pixels)
- ✅ Inverse polynomial fitted: `Reprojection Error : 0.0090`

**Output files created:**
```
output/<camera-name>/
├── calibration/
│   └── calibration_<camera-name>.json    # Calibration parameters
├── corners_detection/
│   └── corner_detections_<camera-name>.pickle
├── reprojections/
│   └── reprojection_*.png                 # Per-image reprojection overlays
├── Mean_reprojection_error_<camera-name>.png
└── Model_projection_<camera-name>.png
```

### Alternative: pip with virtualenv (No uv required)

For users who prefer standard Python tooling, you can set up the project using `pip` and `venv`:

```bash
# 1. Clone the repository
git clone https://github.com/jakarto3d/py-OCamCalib.git
cd py-OCamCalib

# 2. Create a virtual environment (requires Python 3.13+)
python3.13 -m venv .venv

# 3. Activate the virtual environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# 4. Install dependencies from requirements.txt (pinned versions)
pip install --upgrade pip
pip install -r requirements.txt

# 5. Install the package in editable mode
pip install -e .

# 6. Verify installation
python -c "import pyocamcalib; print('Py-OCamCalib ready!')"

# 7. Run calibration
python -m pyocamcalib.script.calibration_script /path/to/chessboard/images 9 5 --camera-name mycam --square-size 35
```

**Note**: This project requires **Python 3.13 or later**. The `requirements.txt` file contains pinned dependency versions for reproducible installations.

## Example

./test_images contains images of chessboard pattern taken from three different fisheye lenses.
You can use them to test the project.

**Note**: When using uv, run commands with `uv run python -m pyocamcalib.script.calibration_script` instead of `python calibration_script.py`.

### Use case 1: Automatic detection (no manual check)

```bash
# With uv
uv run python -m pyocamcalib.script.calibration_script ./test_images/fish_1 8 6 --camera-name fisheye_1

# Without uv (if using conda/virtualenv)
python -m pyocamcalib.script.calibration_script ./test_images/fish_1 8 6 --camera-name fisheye_1
```

### Use case 2: Automatic detection with manual verification

```bash
uv run python -m pyocamcalib.script.calibration_script ./test_images/fish_1 8 6 --camera-name fisheye_1 --check
```

⚠️ **Manual corner verification is not very intuitive!**

*Instructions*:

Once the OpenCV window opens, you can enter two different modes: SELECTION MODE and DRAW MODE.
 
 - **SELECTION MODE**: Press 's' to enter. This allows you to select points that were not detected accurately. After pressing 's', surround such points with a bounding box by pressing the left mouse button, draw the bounding boxes, **AND** confirm by pressing Enter. Once you've selected all your points, quit selection mode by pressing 'esc'. Selected points should appear in RED.

 - **DRAW MODE**: Press 'd' each time you want to draw a new point, then click to place your modified points. New points must be drawn in the same order as the selected points.

 When done, press 'z' to quit. A window with your modified pattern should appear.

### Use case 3: Load corners from file

```bash
uv run python -m pyocamcalib.script.calibration_script ./test_images/fish_1 8 6 --camera-name fisheye_1 --corners-path ./checkpoints/corners_detection/detections_fisheye_1_09092022_053310.pickle
```

## Some notes about the implementation and the camera model (WIP)

## Fisheye camera model
The Computer Vision Toolbox calibration algorithm uses the fisheye camera model proposed by Scaramuzza. 
The model uses an omnidirectional camera model. The process treats the imaging system as a compact system. 
In order to relate a 3-D world point on to a 2-D image, you must obtain the camera extrinsic and intrinsic parameters. 
World points are transformed to camera coordinates using the extrinsics parameters. 
The camera coordinates are mapped into the image plane using the intrinsics parameters.

### Extrinsics parameters
The extrinsic parameters consist of a rotation, R, and a translation, t. The origin of the camera's coordinate system
is at its optical center (the point of intersection of the lens' optical axis with the camera's sensing plane) and 
its x- and y-axis define the image plane. 
<p float="left">
  <img src="./docs/extrinsics_formula.png" width="300" />
  <img src="./docs/extrinsics_schema.png" width="231" />
</p>

### Intrinsics parameters
Intrinsics parameters allow to map world point [Xc, Yc, Zc] from the camera's coordinate system to the image plane in
pixel coordinates.  
There are several canonical fisheye projections to model this projection (stereographic, equidistant, equisolid, ...).
However, it's unlikely that the camera you wish to calibrate fit exactly with these projections. These cameras use a 
complex series of lenses that can't fit accurately to a mathematical model du to physical manufacturing. 
Hence, Scaramuzza's model propose to fit a polynomial to find the accurate function $f(\rho) = \theta$.
<p>
  <img src="./docs/canonical_fisheye_projection.png" width=700" class="center">
</p>

The following equation maps an image point into its corresponding 3-D vector.
<p>
  <img src="./docs/image_to_3d_vector.png" width=600" class="center">
</p>

The intrinsic parameters also account for stretching and distortion. The stretch matrix compensates for the sensor-to-lens
misalignment, and the distortion vector adjusts the (0,0) location of the image plane.
<p>
  <img src="./docs/stretch_matrix.png" width=400" class="center" title="https://www.mathworks.com/help/vision/ug/fisheye-calibration-basics.html">
</p>

The following equation relates the real distorted coordinates (u'',v'') to the ideal distorted coordinates (u,v).
<p>
  <img src="./docs/stretch_matrix_equation.png" width=400" class="center" title="https://www.mathworks.com/help/vision/ug/fisheye-calibration-basics.html">
</p>

### The inverse polynomial function
The direct polynomial is used to map a point from the image plane into its corresponding 3-D vector. However, you might 
need to the inverse projection to map a 3-D vector in the camera's coordinate into it's corresponding point in the image
plane. On way is to find is to find the solution of the following system of equations :  
<p>
  <img src="./docs/cam2world_system.png" width=500" class="center">
</p>
One need to find the roots of (1), take the minimum of the real one, inject in $\lambda$ and get the couple $(u, v)$.<br/>

One other way, which is much faster, is to fit a polynomial function (which is the so-called inverse polynomial) using 
some samples from the previous method. This mean to get ${(\rho_i, \theta_i)}_{i \in [1, N]}$ using previous method and 
fit a polynom $P$ such that $\forall i \in [1, N], P(\theta_i) = \rho_i $. The degree of $P$ is determined in the following 
way: fix the maximal error $\alpha$ desired and  increase the degree of $P$ until $\sum \frac{|P(\theta_i) - \rho_i|}{N} < \alpha$. <br/>
The number of sample $N$ is not so important, $N\approx100$ give accurate results. However, one should take care to sample 
the incident angle $\theta$ uniformly in $[0, \pi]$ (not until $\pi$ because fitting function may raise poorly 
conditioned warning but almost, $0.9\pi$ give accurate results). Even if the camera cannot have a field of view of 360 degrees,
inverse polynomial should stay consistent (which mean rho have to always increase with theta) for the entire field of view.
Here is an example of strange behavior for $\theta$ sampled between $[0, 0.6\pi]$:
<p>
  <img src="./docs/inverse_poly_bad_fitting.png" width=600" class="center">
</p>

Here is the same for $\theta$ sampled between $[0, 0.9\pi]$, now result is consistent:
<p>
  <img src="./docs/inverse_poly_good_fitting.png" width=600" class="center">
</p>

### Image projection conversion

This section describe the process where the initial fisheye image is projection-transformed into a Rectilinear image. <br/>
This process is often referred as "image distortion correction" but this appellation poorly makes sense and can be really confusing. In the literature, perpective 
(aka rectilinear) projection is generally considered to be the Reference, and so the convention is to talk about "unwanted distortion"
and "correction" each time projection differ from this ideal (i.e. a straight line must be straight).  <br/>
However, if you take a fisheye camera that perfectly follow an ideal equidistant projection, why should we talk about
"distortion" or "correction" ? In this case, we should talk about distortion the equidistant projection model that we use for our camera doesn't exactly fit with our camera, 
so we may want to correct or distort our model to fit exactly with it.
And then, for a project, we may need to CONVERT image from this camera to Rectilinear image. <br/>
That why I prefer to talk about Image projection CONVERSION than "UNDISTORTION" to refer to the process of fisheye-rectilinear transformation.<br/>
<a href="http://michel.thoby.free.fr/Fisheye_history_short/Projections/Fisheye_projection-models.html">Here is an interesting article on the subject.

<p float="left">
  <img src="./docs/original_fisheye.png" width="400" />
  <img src="./docs/conversion_perspective_projection.png" width="317" />
</p>

```bash
# With uv
uv run python -m pyocamcalib.script.projection_conversion_script ../../../test_images/fish_1/Fisheye1_1.jpg ../checkpoints/calibration/calibration_fisheye_1_18052022_154907.json 80 700 700

# Without uv
python -m pyocamcalib.script.projection_conversion_script ../../../test_images/fish_1/Fisheye1_1.jpg ../checkpoints/calibration/calibration_fisheye_1_18052022_154907.json 80 700 700
```

**Arguments**: `<fisheye_image> <calibration_json> <fov_degrees> <output_height> <output_width>`


