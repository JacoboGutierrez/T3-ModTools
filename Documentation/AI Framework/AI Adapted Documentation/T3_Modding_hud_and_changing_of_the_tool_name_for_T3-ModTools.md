# T3 MODDING Transcripción completa del chat

Visión azul del T-900 Heavy, automatización de parches y T3-ModTools

Conversación del 8 de agosto de 2026

## Transcripción

Este PDF reproduce los mensajes visibles del chat en orden cronológico, incluidos los mensajes de progreso y las referencias a archivos generados. No incluye razonamiento interno ni llamadas de herramientas.

## Usuario · 2026-08-08 20:39 ART

La tecla Q activa la vision de terminator roja en nidades terminator sabes donde esta el archivo que controla eso? Por que quiero que a diferencia del resto de terminators el T-900 heavy tenga vision en color azul cuando se presione esa tecla.

## ChatGPT

Voy a revisar el contenido de T3.zip buscando dos cosas: el archivo que define la visión Terminator al pulsar Q y si esa lógica distingue entre T900S y T900Heavy. Si está centralizada, también te digo cuál sería la forma más limpia de darle azul solo al Heavy.

## ChatGPT

Ya apareció una pista muy fuerte en el ejecutable: la función usa los estados `NIGHTVISION_ON` / `NIGHTVISION_OFF`, y el HUD carga MenuDatas\hud.dat junto con efectos HudEffect\Sotet.fv, Hangya.fv y Villan.fv. Además, el ejecutable reconoce por separado T900Heavy y T900S, así que hay posibilidades reales de hacer la excepción por clase y no recolorear a todos los Terminators.

## ChatGPT

Encontré algo importante en MenuDatas\hud.dat: existe un bloque llamado `LayerTerminatorVision` y dentro hay incluso una imagen Vision preparada como filtro de pantalla con color 00FF0000 (rojo), aunque en esta versión está comentada. Eso indica que el color de visión está ligado al HUD/efecto Terminator, no al .dat individual de T900Heavy. Ahora estoy separando qué parte es configurable y qué parte está codificada en T3.exe.

## ChatGPT

Encontré el archivo que realmente explica el tinte rojo del mundo, y es más directo que el HUD: Autoexec\autoexec.cfg. Ahí existe un perfil separado llamado `SkyNet_Gamma` con valores RGB muy desbalanceados hacia el rojo; además el PDB confirma funciones SetGamma_Skynet, SetGamma_T1, SetGamma_Human y SetGammaType. Esto encaja exactamente con la visión que se activa con Q.

## ChatGPT

Sí. Revisando el T3.zip encontré exactamente de dónde sale esa visión roja.

La visión activada con Q no depende principalmente de T900Heavy.dat ni del HUD. El color del mundo se genera mediante un perfil de gamma RGB.

### Archivo que controla el color

En la versión parcheada del juego, el archivo efectivo es:

```text
Patch116.Cod
└── Autoexec
    └── autoexec.cfg
```

También existe en Game.cod, pero Patch116.Cod contiene la misma ruta y tiene prioridad.

Dentro aparece esto:

```text
SkyNet_Gamma.Gamma_R 0.36
SkyNet_Gamma.Brightness_R -0.65
SkyNet_Gamma.Contrast_R 2.9
SkyNet_Gamma.Overbright_R 1.0
```

```text
SkyNet_Gamma.Gamma_G 1.8
SkyNet_Gamma.Brightness_G -0.65
SkyNet_Gamma.Contrast_G 1.5
SkyNet_Gamma.Overbright_G 1.0
```

```text
SkyNet_Gamma.Gamma_B 1.8
SkyNet_Gamma.Brightness_B -0.65
SkyNet_Gamma.Contrast_B 1.1
SkyNet_Gamma.Overbright_B 1.0
```

Ese `SkyNet_Gamma` es la visión roja de los Terminators.

El PDB además confirma que T3.exe tiene estas funciones:

```text
SetGamma_Simple
SetGamma_Skynet
SetGamma_T1
SetGamma_Human
SetGammaType
```

y para la tecla/modo especial:

```text
cBase::SetSpecialView
cBase::SpecialView
cBase::oldSpecialView
cHudManager::SpecialView
```

El código original estaba en:

```text
C:\code\build\T3\Code\Game\cBase_Player.cpp
```

Por tanto la cadena es aproximadamente:

```text
Q
 ↓
cBase::SetSpecialView()
 ↓
SpecialView = ON
 ↓
SetGammaType(...)
 ↓
SetGamma_Skynet()
 ↓
SkyNet_Gamma.* de Autoexec\autoexec.cfg
```

### Podemos comprobarlo fácilmente

Como prueba, podríamos hacer que todos los Terminators tengan visión azul intercambiando básicamente los parámetros rojo/azul:

```text
SkyNet_Gamma.Gamma_R 1.8
SkyNet_Gamma.Brightness_R -0.65
SkyNet_Gamma.Contrast_R 1.1
SkyNet_Gamma.Overbright_R 1.0
```

```text
SkyNet_Gamma.Gamma_G 1.8
SkyNet_Gamma.Brightness_G -0.65
SkyNet_Gamma.Contrast_G 1.5
SkyNet_Gamma.Overbright_G 1.0
```

```text
SkyNet_Gamma.Gamma_B 0.36
SkyNet_Gamma.Brightness_B -0.65
SkyNet_Gamma.Contrast_B 2.9
SkyNet_Gamma.Overbright_B 1.0
```

Eso debería producir una versión azul aproximadamente equivalente al efecto rojo original.

### Pero para hacerlo solo en T-900 Heavy

Aquí está la parte interesante: T900Heavy y T900S sí están separados internamente. El PDB contiene explícitamente:

```text
SOLDIER_T900S
SOLDIER_T900HEAVY
```

Sin embargo, ambos terminan utilizando el mismo:

```text
SetGamma_Skynet()
```

y por tanto el mismo SkyNet_Gamma.

Así que modificar solamente:

```text
Autoexec\autoexec.cfg
```

haría azul la visión de todos los Terminators que usan SkyNet_Gamma.

La solución correcta para nuestro mod sería añadir una excepción en T3_Modded.exe:

```text
if (playerType == SOLDIER_T900HEAVY)
{
    SetGamma_HeavyBlue();
}
else
{
    SetGamma_Skynet();
}
```

Conceptualmente podríamos tener:

```text
SkyNet_Gamma = rojo original
T900Heavy_Gamma = azul
```

y mantener intactos:

```text
T900S → rojo
T900Heavy → azul
T1 → T1_Gamma
Humanos → Human_Gamma
```

Además encontré LayerTerminatorVision en MenuDatas\hud.dat con un antiguo filtro rojo, pero la imagen `Vision` está comentada, así que no parece ser la responsable del efecto actual. La evidencia del ejecutable apunta claramente al sistema SetGamma_Skynet.

Yo atacaría esto igual que hicimos con el WM20: primero podemos hacer un test global azul de `SkyNet_Gamma` para confirmar visualmente al 100 % que es el efecto que buscas, y después localizar la rama de T3.exe donde se asigna GammaType para convertirla en una excepción exclusiva del

```text
T900Heavy.
```

## Usuario · 2026-08-08 20:51 ART

como se puede hacer para hacer el modding mas automatico, por que la gente se descarga el mod y va a tener que hacer parches del launcher modded y la gente no sabe hacer eso. Ademas si en el mod les dieramos un launcher ya modificado para este mod, las personas que quieran usarlo con otro mod que altera el launcher modded van a necesitar un launcher para ese otro mod y ese otro mod les cancelaria este launcher.

## ChatGPT

Sí: la solución debería ser que ningún mod distribuya su propio `T3_Modded.exe`. El launcher

modificado tendría que generarse automáticamente a partir de todos los mods activos, igual que ya compilamos Mods.Cod. Voy a aterrizarlo sobre la estructura actual de T3 Asset Tool para que podamos integrarlo sin romper el sistema de load order.

## ChatGPT

La clave es separar “el mod” de “el ejecutable resultante”. Un mod debería traer únicamente instrucciones de parcheo; T3 Asset Tool toma un ejecutable base limpio y construye un único T3_Modded.exe combinando los parches de todos los mods habilitados. Así activar otro mod no reemplaza el ejecutable: obliga a recompilarlo con A + B + C.

## ChatGPT

Sí. La solución más sólida es convertir T3 Asset Tool en un compilador de mods, no en un sistema donde cada mod distribuya su propio ejecutable parcheado.

Ahora mismo el problema conceptual es este:

```text
Mod A
└── T3_Modded.exe con parche A
```

```text
Mod B
└── T3_Modded.exe con parche B
```

Instalás B y perdés A.

Deberíamos pasar a:

```text
T3.exe ORIGINAL
      │
      ├── parche del Mod A
      ├── parche del Mod B
      ├── parche del Mod C
      │
      ▼
T3_Modded.exe
A + B + C
```

### Cómo lo implementaría en T3 Asset Tool

Cada mod podría tener algo así:

```text
mods/
└── T900 Heavy Blue Vision/
    ├── mod.json
    ├── files/
    │ └── ...
    └── patches/
        └── executable.json
```

Y executable.json no contendría un .exe, sino instrucciones:

```text
{
    "target": "T3.exe",
    "patches": [
        {
            "id": "t900heavy_blue_vision",
            "type": "code_patch",
            "pattern": "8B ?? ?? ?? ?? 85 C0 74 ??",
            "expected_matches": 1,
            "patch_file": "t900heavy_blue_vision.bin"
        }
    ]
}
```

La idea importante es que el mod diga:

«Buscá esta parte del código y aplicá este cambio».

En lugar de:

«Reemplazá todo el ejecutable por este otro».

### Al darle a Compile Mods

T3 Asset Tool haría automáticamente:

```text
1. Leer T3.exe original limpio
2. Crear una copia temporal
3. Leer mods habilitados
4. Ordenarlos por Load Order
5. Aplicar todos los patches ejecutables
6. Detectar conflictos
7. Generar Mods.Cod
8. Generar T3_Modded.exe
```

Resultado:

```text
T3_Modded.exe
Mods.Cod
```

Y el usuario solamente tendría:

```text
[✓] T900 Heavy
[✓] Blue Heavy Vision
[✓] Longer Corpses
[✓] WM20 Blue Plasma
[✓] Otro mod de código
```

```text
[ Compile / Play ]
```

No tendría que saber absolutamente nada de hexadecimal, patching o executables.

### Nunca parchear `T3_Modded.exe` encima de sí mismo

Esto es muy importante.

Cada compilación debería empezar siempre desde:

```text
T3.exe
```

original.

Nunca:

```text
T3_Modded.exe
    ↓
volver a parchearlo
```

Porque terminaríamos acumulando modificaciones y sería muy difícil saber qué mod hizo qué.

Sería:

```text
T3.exe original
```

```text
A + B + C
    ↓
T3_Modded.exe
```

```text
desactivo B
```

```text
T3.exe original
```

```text
A + C
    ↓
T3_Modded.exe
```

Esto haría también que desinstalar mods sea trivial.

### Detección automática de conflictos

El patcher debería llevar un mapa interno de qué mod modifica cada dirección.

Por ejemplo:

```text
Mod A:
0x0045A100 - 0x0045A107
```

```text
Mod B:
0x00521D30 - 0x00521D34
```

No hay problema.

T3 Asset Tool muestra:

```text
Executable patches: OK
```

Pero si:

```text
Mod A:
0x0045A100 - 0x0045A107
```

```text
Mod B:
0x0045A104 - 0x0045A110
```

hay solapamiento.

Entonces:

```text
Executable Patch Conflict
```

```text
T900 Heavy Blue Vision
        conflicts with
Alternative Terminator Vision
```

```text
Function:
SetGamma_Skynet
```

```text
[Disable A] [Disable B]
```

Muchísimo mejor que simplemente dejar que el segundo mod destruya silenciosamente el primero.

### Incluso podemos distinguir conflictos reales

Si dos mods escriben exactamente lo mismo:

```text
Mod A → 90 90 90 90
Mod B → 90 90 90 90
```

no necesariamente es un conflicto.

Podemos marcarlo:

```text
Shared identical patch - OK
```

Pero:

```text
Mod A → 90 90 90 90
Mod B → E9 34 52 00
```

sí:

```text
Conflict
```

### No usaría solamente offsets

Algo como:

```text
offset 0x0045A123
```

funciona, pero es frágil.

Preferiría que nuestros mods puedan usar AOB signatures/patterns:

```text
8B 45 ?? 83 F8 02 75 ?? D9 05 ?? ?? ?? ??
```

El Asset Tool busca esa secuencia en el ejecutable.

Entonces podemos comprobar:

```text
Expected matches: 1
Found matches: 1
```

```text
Patch OK
```

Si el usuario tiene una versión incompatible:

```text
Expected matches: 1
Found matches: 0
```

```text
T3.exe version incompatible with:
T900 Heavy Blue Vision
```

Y no destruimos su ejecutable.

También podemos verificar el SHA-256 del T3.exe conocido.

### Para cambios grandes hay algo todavía mejor

A largo plazo yo haría un T3 Mod Loader universal.

Algo así:

```text
T3_Modded.exe
      │
      ▼
T3ModLoader.dll
      │
      ├── Mod A
      ├── Mod B
      ├── Mod C
      └── Mod D
```

En ese diseño T3_Modded.exe no contiene las características específicas de los mods.

Solo sabe:

```text
iniciar T3
cargar T3ModLoader
cargar mods habilitados
aplicar hooks
continuar ejecución
```

Por ejemplo, nuestro mod de visión podría tener:

```text
mods/
└── T900HeavyBlueVision/
    ├── mod.json
    └── patches/
        └── specialview.json
```

Y en memoria:

```text
cBase::SetSpecialView
        │
        ▼
T3 Mod Loader
        │
        ├── jugador == T900Heavy
        │ └── Gamma azul
        │
        └── otro Terminator
```

```text
└── SetGamma_Skynet original
```

Esto es mucho más escalable.

### Y hay otra ventaja enorme

Podríamos crear hooks compartidos.

Supongamos que dentro de un año tenemos:

```text
Blue Heavy Vision
Thermal Vision Mod
Night Vision Improvements
HUD Improvements
```

y todos quieren modificar:

```text
cBase::SetSpecialView
```

En lugar de que los cuatro parcheen esa función, solamente la parchea una vez:

```text
T3ModLoader
        │
        ▼
SpecialView Hook
```

y los mods registran comportamiento:

```text
SpecialView
 ├─ callback BlueHeavyVision
 ├─ callback ThermalVision
 └─ callback HudImprovement
```

Ese sería prácticamente el equivalente de crear una pequeña API de modding para T3.

### Yo lo desarrollaría en dos etapas

Primero, añadiría a nuestro actual T3 Asset Tool el sistema de Executable Patch Manifests. Es bastante compatible con lo que ya tenemos:

```text
files/ → Mods.Cod
```

```text
patches/ → T3_Modded.exe
mod.json → metadata/load order
```

Un único botón recompila ambos.

Luego haría el T3 Mod Loader, para que las modificaciones más complejas de funciones C++ puedan implementarse mediante hooks sin tener que escribir cada vez más modificaciones directamente sobre

```text
T3.exe.
```

Nuestro mod actual del T-900 Heavy con visión azul sería un excelente primer caso real para desarrollar el nuevo sistema: en vez de entregarte un T3_Modded.exe especial, podríamos hacer que T3 Asset Tool genere un pequeño patch t900heavy_blue_vision y demostrar que puede coexistir con los futuros parches de cadáveres, sonido, nuevas unidades, etc.

## Usuario · 2026-08-08 20:55 ART

estamos sobreescribiendo el T3.exe?

## ChatGPT

No. En el sistema que venimos usando, `T3.exe` se conserva intacto.

T3 Asset Tool trabaja con esta idea:

```text
T3.exe ← original, no se toca
T3_Modded.exe ← ejecutable generado/parcheado para los mods
Mods.Cod ← archivos de los mods compilados
```

Y mi propuesta anterior mantiene exactamente esa regla. Cuando recompilamos los mods, lo correcto sería volver a tomar como base el T3.exe original y generar de nuevo:

```text
T3.exe original
   +
parche A
   +
parche B
   +
parche C
   ↓
T3_Modded.exe
```

Nunca deberíamos parchear directamente T3.exe, ni usar el T3_Modded.exe anterior como base para la siguiente compilación.

Así, si algo sale mal, el usuario siempre conserva el juego original y puede ejecutarlo normalmente.

## Usuario · 2026-08-08 20:58 ART

bueno podrias parchear el asset tool y hacemos la prueba? Necesitas que te pase la ultima version del asset tool?

## ChatGPT

Sí, podemos hacer la prueba. Primero voy a comprobar si la última versión del Asset Tool ya está dentro de lo que me pasaste; si no está, ahí sí necesitaremos que me subas el ZIP actual del tool para parchear esa versión exacta.

## ChatGPT

Sí, necesito que me pases la última versión del T3 Asset Tool.

El T3.zip que tengo ahora contiene el juego (T3.exe, Game.cod, Patch116.Cod, etc.), pero no contiene el Asset Tool.

Subime el ZIP actual del tool y voy a parchear esa versión para una primera prueba con esta lógica:

```text
T3.exe original
      ↓
copiar
      ↓
aplicar parches de mods habilitados
      ↓
T3_Modded.exe
```

Para esta primera implementación mantendría el alcance controlado: soporte de parches de ejecutable dentro de cada mod, recompilación siempre desde el T3.exe original y detección básica de conflictos. Después podemos usar el T-900 Heavy con visión azul como primer mod real de prueba.

## Usuario · 2026-08-08 21:00 ART

Tambien quiero que se llame T3-ModTools

[Archivo subido: T3_Asset_Tool.zip]

## ChatGPT

Perfecto. Voy a tomar esta última versión como base, renombrar el proyecto visible a T3-ModTools y añadir el primer soporte para que los mods puedan aportar parches al ejecutable sin distribuir su propio T3_Modded.exe. Primero voy a inspeccionar cómo está armado el compilador actual para integrarlo donde ya genera Mods.Cod y T3_Modded.exe.

## ChatGPT

La versión actual ya tiene una buena base: el loader se genera siempre desde `T3.exe` original, pero el proceso está separado en “Build Mods.Cod” e “Install Mod Loader”. Voy a unificar eso y extender

mod.json/files/ con una carpeta patches/, de modo que Build Mods reconstruya tanto Mods.Cod como T3_Modded.exe en una sola operación.

## ChatGPT

La primera parte ya está integrada: los proyectos nuevos ahora tienen files/ y patches/, el listado muestra cuántos parches EXE aporta cada mod y Build Mods + Modded EXE reconstruye todo automáticamente. También agregué detección de solapamientos: dos mods no pueden escribir bytes incompatibles en la misma zona del ejecutable sin que la herramienta lo detecte y detenga la compilación.

## ChatGPT

La compilación automática ya pasó una prueba real usando el T3.exe de tu ZIP: generó un Mods.Cod válido para un mod que solo aporta un parche EXE, creó T3_Modded.exe, aplicó el manifiesto y comprobó por SHA-256 que `T3.exe` quedó byte por byte intacto. Ahora estoy cerrando detalles de seguridad para que una compilación fallida no deje mezclados un Mods.Cod nuevo con un ejecutable anterior.

## ChatGPT

Listo. Parcheé y renombré la herramienta como T3-ModTools 0.6.0.

Archivo generado: T3-ModTools-0.6.0.zip

Los cambios principales son:

- La aplicación y los launchers ahora se llaman T3-ModTools.

```text
• T3-ModTools.bat y T3-ModTools.vbs.
```

- Los proyectos de mods ahora admiten: `text My_Mod/ ├── mod.json ├── files/ └── patches/ └── executable.json `

- El botón ahora es Build Mods + Modded EXE.

- Una sola compilación genera automáticamente: `text mods/Mods.Cod T3_Modded.exe

`

- Siempre parte del `T3.exe` original.

- Nunca modifica T3.exe.

- Ya no hay que ir aplicando manualmente un launcher distinto por cada mod.

- Varios mods pueden aportar parches al mismo T3_Modded.exe.

- Añadí patrones AOB con ?? como wildcard.

- Comprueba que la firma aparezca exactamente una vez.

- Detecta conflictos entre parches de diferentes mods.

- Si una compilación falla, restaura juntos el Mods.Cod y T3_Modded.exe anteriores para no dejar una combinación inconsistente.

- También acepta mods que solamente modifican el EXE, aunque no tengan archivos para Mods.Cod.

Lo probé directamente contra el T3.exe de tu T3.zip. La prueba confirmó que se genera T3_Modded.exe, se aplica un parche desde un mod, se detectan conflictos y el SHA-256 del `T3.exe` original permanece exactamente igual.

Incluí además:

```text
EXECUTABLE_PATCHES.txt
```

con la documentación del nuevo formato.

La limitación actual es que v0.6.0 admite parches ejecutables de tipo AOB replacement del mismo tamaño. Para el caso concreto:

```text
T900S → visión roja
T900Heavy → visión azul
```

probablemente necesitaremos el siguiente tipo de parche: hook + code cave, porque hay que introducir una condición según el tipo de unidad y no simplemente sustituir unos bytes globales.

Ese puede ser el siguiente paso y serviría como primer mod real que pruebe el nuevo sistema multi-parche.

## Usuario · 2026-08-08 21:30 ART

me darias un archivo con el mod de modificacion del hud a azul para el t900heavy?

## ChatGPT

Sí. Voy a prepararlo como un mod instalable de T3-ModTools, no como un T3_Modded.exe aparte. Voy a comprobar primero si podemos hacer el azul exclusivo del T900Heavy con datos/HUD; si requiere el hook que comentamos, incluiré también el parche ejecutable necesario dentro del propio mod.

## ChatGPT

Hay dos componentes distintos en esa visión: el overlay del HUD y el tinte/gamma rojo del mundo. Para que el Heavy quede realmente azul sin cambiar a los demás Terminators, el mod tiene que cambiar ambos de forma condicional; un simple hud.dat azul afectaría globalmente a todos.

## ChatGPT

Ya encontré una diferencia útil en el ejecutable: T900S y T900Heavy tienen IDs internos distintos (4 y 5). Además cBase::SetSpecialView actualmente solo habilita esa visión para ciertos tipos, así que podemos enganchar específicamente el ID 5 sin tocar el comportamiento rojo de las otras unidades.

## ChatGPT

Para que la prueba sea visualmente clara, estoy preparando el mod con un HUD alternativo propio del Heavy, en vez de reemplazar MenuDatas/hud.dat globalmente. Así evitamos que un cambio de Piros/overlay termine volviendo azul también al Scout, Supply u otros Terminators.

## ChatGPT

Ya tengo una primera versión viable sin tocar el hud.dat global: el parche intercepta únicamente la carga del HUD y, si DrivedSoldier->type == 5 (T900Heavy), carga MenuDatas\hud_t900heavy.dat; para cualquier otro tipo sigue cargando el HUD original. Esto es exactamente el tipo de mod que queríamos probar con el nuevo sistema automático.

## ChatGPT

Sí. Preparé el primer mod de prueba para T3-ModTools 0.6.0:

Archivo generado: T900Heavy_Blue_HUD_v1.0.0.zip

Este mod hace la selección de forma condicional:

```text
T900Heavy (ID interno 5)
        ↓
MenuDatas\hud_t900heavy.dat
        ↓
overlay Terminator rojo → azul
```

```text
Cualquier otra unidad
        ↓
MenuDatas\hud.dat original
```

No reemplaza globalmente el HUD, así que el cambio está pensado específicamente para el T-900 Heavy. El ZIP contiene mod.json, files/ y patches/executable.json; T3-ModTools genera automáticamente el único T3_Modded.exe.

Para probarlo, extraé la carpeta T900Heavy_Blue_HUD dentro de:

```text
T3/
└── mods/
    └── T900Heavy_Blue_HUD/
```

Luego activalo en T3-ModTools, pulsá Build Mods + Modded EXE, ejecutá T3_Modded.exe, entrá como T-900 Heavy y probá Q.

También hice una compilación de prueba: los 2 parches EXE se aplicaron correctamente, hud_t900heavy.dat entró en Mods.Cod y `T3.exe` permaneció intacto.

Importante para esta primera prueba: este mod cambia específicamente el componente HUD/overlay de la visión. Si al pulsar Q vemos el HUD azul pero el escenario conserva además un tinte rojo, eso confirmará que tenemos un segundo componente proveniente de SetGammaType; en ese caso el siguiente parche será hacer también esa gamma azul exclusivamente para T900Heavy.

## Usuario · 2026-08-08 21:54 ART

dame un pdf de este chat entero

Fin de la transcripción.
