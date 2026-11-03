# Manually adding ANM joints

The ANM importer records the original joint names and order on each Blender Action.
The ANM exporter 0.8.1 preserves that set by default. Keyframes on other bones do
not alter the exported joint list.

In Pose Mode, select one or more bones and use **right-click > (T3) Add Joint to
animation**. The command stores their full T3 hierarchy paths on the active Action,
in armature order. Repeating it does not duplicate joints. The exporter inserts
new ancestors before existing descendants, keeps the original joint order, and
samples their pose matrices at every
exported frame. Animate and keyframe the added bones as usual.

`CA/tps_skynet/t900_run_wm20.anm` from the original Game.Cod has 19 joints.
`t900_run.anm` has 32; its head joint is absent from the WM20 overlay. Adding
the head in Pose Mode makes the exported WM20 animation contain its original 19
joints followed by the head joint. Adding spine ancestors places them before the
original hand and arm joints. Keyframes on any other bones remain excluded.

The joint additions are stored on the Action as `t3_added_joint_names_json`,
separate from the imported `t3_joint_names_json`. They also apply when a Reference
ANM is selected. Keep **Preserve imported ANM joint set** enabled and **Selected
pose bones only** disabled to export the complete original plus manually added set.
Disabling preservation without a reference ANM retains the exporter's explicit
whole-armature behavior.

When an overlay activates joints absent from the previous animation, T3 1.16's
native crossfade can mix global bind data with local ANM data. Reordering joints
does not correct that engine behavior. See [ANM_TRANSITION_FIX.md](ANM_TRANSITION_FIX.md)
for the mod-side correction and pending in-game verification.
