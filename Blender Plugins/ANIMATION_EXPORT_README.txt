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

FOOTSTEPS (Walk Animation)
-------------------------
1. Select the armature and make the desired Action active. T3 animations normally start
   at frame 0: a footstep assigned to Blender frame 11 exports as ANM Frame 11.
2. In the Timeline or Dope Sheet, move the playhead to the desired frame, then right-click.
   Choose AnimationNotify Footstep_Left or AnimationNotify Footstep_Right. The menu
   displays the current frame so you can check the target before assigning the event.
3. Assigning a footstep automatically enables Walk Animation for this Action. You can
   also toggle the checkbox in File > Export > T3 Animation (.anm).
4. Open Dope Sheet > sidebar (N) > T3 > T3 AnimationNotify to see the footsteps, edit
   their frame numbers, or remove them with X. In Action Editor mode they are also
   visible as local Action markers. Save the .blend to preserve the settings and marks.
5. Export. Enabled footsteps are written in AnimationNotify after the Animation block.
   Disabling Walk Animation omits the events but keeps the markers in the Action.

Notes:
- The target is the current playhead frame, not every selected keyframe. You do not
  need to create a bone keyframe just to add a footstep.
- Markers belong to the active armature Action, not the scene. Switching Actions does
  not transfer footstep events to the next animation.
- Reassigning the same foot at the same frame does not create duplicates.
- Multiple frames for the same foot are sorted and grouped under one Frame token.
  The native Notify record holds at most four frames per foot; exceeding this stops
  export rather than overflowing the game's fixed-size frame array.
- An enabled Walk Animation with no footsteps, or a footstep outside the exported
  Action range, stops export with an explanation instead of silently losing events.
- As with poses, a nonzero Action start is subtracted from event frame numbers.
- The ANM importer does not yet import existing AnimationNotify blocks. Assign steps
  manually after importing; for the original 32-frame T900 run, use Left 11 / Right 27.
- Updated exporter version: 0.7.0. Reinstall this .py through Install from Disk and
  restart Blender if the previous exporter is already loaded.

LIMITATIONS
-----------
- Experimental: individual animations can still require axis, rest-pose, or root-motion
  corrections for a specific T3 rig.
- The exporter samples every integer frame in the active Action range and writes the
  native frame count to MaxTimeValue.
- Constraints are evaluated through the final pose matrices. Footstep_Left and
  Footstep_Right are supported with Walk Animation; other game events are not authored.
