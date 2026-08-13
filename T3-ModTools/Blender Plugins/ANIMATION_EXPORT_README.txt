T3 ANM BLENDER EXPORTER
=======================

FILE
----
T3_Blender_ANM_Exporter.py

PURPOSE
-------
This experimental Blender add-on exports the active Action of a compatible armature to
the text-based T3 .anm animation format.

INSTALLATION
------------
1. Open Blender.
2. Select Edit > Preferences > Add-ons.
3. Click Install from Disk.
4. Select T3_Blender_ANM_Exporter.py.
5. Enable T3 ANM Animation Exporter.

EXPORT
------
1. Select the compatible T3 armature.
2. Import the native ANM that you intend to edit and make its Action active.
3. Use File > Export > T3 Animation (.anm).
4. Leave Preserve imported ANM joint set enabled. The exporter will preserve the source
   joint names, joint order, FPS, and upper-body/full-body scope.
5. If the Action was not created by the importer, select a native Reference ANM with the
   same role (for example, the original T-900 WM20 idle/run/fire overlay).
6. Put the resulting .anm file in the correct internal path under the mod project's files/
   folder before compiling Mods.Cod.

LIMITATIONS
-----------
- Experimental: individual animations can still require axis, rest-pose, or root-motion
  corrections for a specific T3 rig.
- The exporter samples every integer frame in the active Action range and writes the
  native frame count to MaxTimeValue.
- Constraints are evaluated through the final pose matrices, but game-specific animation
  events are not generated.
