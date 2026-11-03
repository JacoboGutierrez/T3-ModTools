T3 RIGGED glTF IMPORTER
========================

FILE
----
T3_Blender_GLTF_Importer.py

PURPOSE
-------
This Blender add-on delegates geometry/skin loading to Blender's glTF 2.0 importer and
then restores the canonical T3 SCA identifiers stored in glTF extras. For example, a
Blender object may be displayed as t900 while retaining the exact runtime pair:

    Instance: |t900
    Mesh:     |t900|t900Shape

The identifiers are stored on both the Blender object and its mesh datablock as:
t3_primitive_name, t3_instance_name, t3_mesh_name, and t3_mesh_root.

INSTALLATION
------------
1. Open Blender.
2. Select Edit > Preferences > Add-ons.
3. Click Install from Disk.
4. Select T3_Blender_GLTF_Importer.py and enable T3 Rigged glTF Importer.

IMPORT
------
Use File > Import > T3 Rigged glTF (.gltf/.glb). New glTF files made by T3-ModTools
contain the exact hierarchy metadata and require no additional setting.

"Bone Shape Scale" controls the display scale of the custom bone shapes created by
Blender's native glTF importer. Its T3 default is 0.10 and it does not rescale the mesh,
armature transforms, animation, or canonical hierarchy metadata.

LEGACY glTF FILES
-----------------
Older glTF files only contain names such as model_rigged. For an exact recovery, set
"Legacy SCA/LOD template" to the original character model.sca or model.lod before
importing. Without a template, the add-on creates an explicitly inferred fallback and
shows a warning; it cannot discover a lost original name from the old glTF alone.

EXPORT
------
T3_Blender_SCA_Exporter.py 0.6.0+ prioritizes the exact stored identifiers. The enhanced
0.5.8 exporter also recognizes t3_mesh_root, which is enough for the standard T3
|root|rootShape hierarchy.
