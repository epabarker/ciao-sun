// Degree and radian conversion factors, one of each for the app.
//
// Multiply by these, as Python's math.radians and math.degrees do, so the JS
// and the reference give the same doubles.

/** Degrees -> radians: multiply by pi/180. */
export const RADIANS_PER_DEGREE = Math.PI / 180;
/** Radians -> degrees: multiply by 180/pi. */
export const DEGREES_PER_RADIAN = 180 / Math.PI;
