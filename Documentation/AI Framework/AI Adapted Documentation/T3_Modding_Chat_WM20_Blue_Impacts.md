# T3 Modding - Impactos plasma azules para WM20 y Termcannon

Transcripción del chat sobre lazerglowred01.tga, BulletHitPlasmaBlue.dat, parcheo de T3_Modded.exe y enrutamiento de impactos azules.

Conversación: 3 de agosto de 2026 - 9 de agosto de 2026

## Usuario · 2026-08-03 10:11:37

donde esta el archivo que le asigna lazerglowred01.tga al laser que dispara el arma "T_RSB80", "rsb80" y al arma primaria de la unidad "FK"?

## ChatGPT · actualización

Voy a rastrear `lazerglowred01.tga` dentro del contenido de T3 y cruzarlo con `T_RSB80`, `rsb80` y la configuración del `FK`. Así podemos distinguir si la textura se asigna directamente en el arma, en un efecto/proyectil o en un material compartido.

## ChatGPT · actualización

El ZIP efectivamente contiene el `Game.cod` completo, no los assets ya extraídos. Encontré dentro del índice referencias a `CA/casts/Fk.dat` y a todas las animaciones `Rsb80`, así que ahora estoy entrando al `.cod` para localizar la cadena de efectos/materiales que conecta esas armas con el láser rojo.

## ChatGPT · actualización

Ya apareció el archivo clave: **`Particles/FiredBullet.dat`**. Ahí se asigna explícitamente `Textures\Particles\lazerglowred01.tga` tanto al efecto `Weapon_RSB80` como a `Weapon_FKPlasma`; estoy verificando ahora cómo `T_RSB80` y `FK0` llegan a esos dos bloques para darte la cadena completa, no solo el archivo final.

## ChatGPT

Sí. Encontré exactamente dónde se asigna.

El archivo que controla **la textura del proyectil/láser visible mientras viaja** es:

```text
Particles/FiredBullet.dat
```

Para **`rsb80` y `T_RSB80`**, ambos terminan usando el bloque:

```text
Weapon_RSB80
{
    TextureSide Textures\Particles\lazerglowred01.tga
    TextureFront Textures\Particles\Muzzle-Front-Plasma.tga
    ParticleSideSizeX 5.00
    ParticleSideSizeY 0.6
    ParticleFrontSize 0.6
    ParticleFrontPosition 0.75
    OpacityMinDistance 17.0
    OpacityMaxDistance 20.2
}
```

La razón por la que **`rsb80` y `T_RSB80` comparten ese efecto** está en sus respectivos:

```text
weapons/rsb80/weapon1.option
weapons/T_RSB80/weapon1.option
```

Ambos tienen:

```text
type bullet
subType 0
```

Ese subtipo corresponde en el engine al efecto **RSB80 -> `Weapon_RSB80`** de `FiredBullet.dat`.

### FK: arma primaria

El cast está definido en:

```text
CA/casts/Fk.dat
```

y dice:

```text
WeaponNumber 2
```

```text
cWeapon
{
    Slot 0
    Name "FK0"
}
```

```text
cWeapon
{
    Slot 1
    Name "FK1"
}
```

Por lo tanto, **el arma primaria del FK es `FK0`**.

Su configuración:

```text
weapons/FK0/weapon1.option
```

usa:

```text
type bullet
subType 16
```

Ese subtipo corresponde al efecto **FK Plasma**, que en:

```text
Particles/FiredBullet.dat
```

es este bloque:

```text
Weapon_FKPlasma
{
    TextureSide Textures\Particles\lazerglowred01.tga
    TextureFront Textures\Particles\Muzzle-Front-Plasma.tga
    ParticleSideSizeX 10.00
    ParticleSideSizeY 0.60
    ParticleFrontSize 0.60
    ParticleFrontPosition 0.75
    OpacityMinDistance 8.0
    OpacityMaxDistance 8.5
}
```

Así que la relación queda:

```text
rsb80
 -> weapon1.option
     -> subType 0
         -> Weapon_RSB80
             -> Particles/FiredBullet.dat
                 -> lazerglowred01.tga
```

```text
T_RSB80
 -> weapon1.option
     -> subType 0
         -> Weapon_RSB80
             -> Particles/FiredBullet.dat
                 -> lazerglowred01.tga
```

```text
FK
 -> CA/casts/Fk.dat
     -> Slot 0 = FK0
         -> weapon1.option
             -> subType 16
                 -> Weapon_FKPlasma
                     -> Particles/FiredBullet.dat
                         -> lazerglowred01.tga
```

Y la textura física está en:

```text
Textures/Particles/lazerglowred01.tga
```

Importante: **`Particles/MuzzleFire.dat` no es el láser que viaja**. Ese archivo controla el fogonazo/efecto en la boca del arma. Para cambiar el color o aspecto del rayo disparado, el archivo que querés modificar es **`Particles/FiredBullet.dat`**.

## Usuario · 2026-08-03 10:34:49

como puedo hacer que el arma Weapon_Wm20 busque un BulletHitPlasmaBlue.dat que he creado en lugar de BulletHitPlasma.dat por defecto?

## ChatGPT · actualización

Voy a seguir la cadena exacta de `Weapon_Wm20`: configuración del arma -> subtipo de impacto/proyectil -> archivo `BulletHit*.dat`. Si el nombre está hardcodeado en una tabla global, te indico qué entrada duplicar o qué índice cambiar para apuntar a `BulletHitPlasmaBlue.dat`.

## ChatGPT · actualización

Encontré algo importante: `BulletHitPlasma.dat` **no parece ser elegido por nombre desde `weapon1.option`**. El nombre `Particles/BulletHitPlasma.dat` está embebido directamente dentro de `T3.exe`, junto a `Particles/BulletHit.dat`, así que el juego carga esas tablas globalmente y luego el arma sólo envía un tipo/subtipo de impacto. Estoy comprobando si existe un índice libre/reutilizable que permita hacerlo sin parchear el EXE.

## ChatGPT · actualización

La estructura del motor confirma que hay **24 tipos de impacto cargados: 12 normales + 12 plasma**. Primero carga `BulletHit.dat` y después `BulletHitPlasma.dat`; no hay una tercera ranura/archivo configurable. Eso significa que simplemente crear `BulletHitPlasmaBlue.dat` dentro del `.cod` no hará que el juego lo lea.

## ChatGPT

En el T3 original **no podés indicarlo desde `weapons/WM20/weapon1.option`**. Revisando el ejecutable y los DAT encontré por qué.

`WM20` está definido así:

```text
weapons/WM20/weapon1.option
```

```text
type bullet
subType 1
```

Ese `subType 1` hace que el proyectil visual use:

```text
Weapon_Wm20
```

de:

```text
Particles/FiredBullet.dat
```

Pero **el efecto de impacto no contiene una ruta a un archivo `BulletHit...dat` en la definición del arma**.

El motor carga globalmente solamente estas dos tablas:

```text
Particles/BulletHit.dat
Particles/BulletHitPlasma.dat
```

y esto está **hardcodeado en `T3.exe`**.

Además, pude confirmar cómo está organizada internamente la tabla:

```text
0 - 11 = BulletHit.dat
12 - 23 = BulletHitPlasma.dat
```

Son los mismos 12 tipos de superficie:

```text
Aluminium
AluminiumOther
Steel
SoftSoil
HardSoil
```

```text
HardSoilParts
Concrete
ConcreteParts
Glass
Wood
Blood
BloodOther
```

Para plasma el juego simplemente usa la segunda mitad de esa tabla.

Por eso esto:

```text
Particles/BulletHitPlasmaBlue.dat
```

aunque esté perfectamente incluido en `Game.cod` o `Mods.Cod`, **nunca será cargado automáticamente**. El ejecutable no busca archivos `BulletHit*.dat`; busca esos dos nombres concretos.

### Lo importante para tu objetivo

Si querés:

```text
RSB80 / FK / WM25 / etc.
        ↓
BulletHitPlasma.dat
```

```text
WM20
        ↓
BulletHitPlasmaBlue.dat
```

necesitamos **modificar `T3_Modded.exe`**, no solamente los DAT.

Y no conviene hacer simplemente un reemplazo hexadecimal de:

```text
Particles/BulletHitPlasma.dat
```

por:

```text
Particles/BulletHitPlasmaBlue.dat
```

porque eso haría:

```text
TODAS LAS ARMAS PLASMA
        ↓
BulletHitPlasmaBlue.dat
```

no solamente `Weapon_Wm20`.

De hecho, en el `T3.exe` original encontré la cadena:

```text
Particles/BulletHitPlasma.dat
```

en:

```text
File offset: 0x2683F0
VA: 0x006683F0
```

y el código la referencia, entre otros sitios, aproximadamente en:

```text
0x004BA658
0x004BB0D2
```

Ahí literalmente ocurre algo equivalente a:

```text
push 006683F0 ; "Particles/BulletHitPlasma.dat"
call ...
```

Así que queda bastante confirmado que es una carga global.

### Cómo lo haría para WM20 exclusivamente

La solución limpia para nuestro sistema de mods sería ampliar **`T3_Modded.exe`** para tener una tercera familia:

```text
0 - 11 BulletHit.dat
12 - 23 BulletHitPlasma.dat
24 - 35 BulletHitPlasmaBlue.dat
```

y después modificar la lógica de `BulletHit`:

```text
si projectile SubType == 1 ; WM20
    BulletHitType += 24
```

```text
else if es plasma
    BulletHitType += 12
else
    BulletHitType += 0
```

Eso sería especialmente bueno porque **WM20 ya tiene una identificación perfecta y exclusiva**:

```text
WM20
type bullet
subType 1
```

mientras que:

```text
RSB80 -> subType 0
WM20 -> subType 1
M4 -> subType 2
M82A1 -> subType 3
...
WM25 -> subType 11
...
FK0 -> subType 16
```

Por lo tanto no necesitamos identificar el arma por nombre `"WM20"` en tiempo de ejecución: podemos detectar simplemente **`SubType == 1`**.

**Mi recomendación es hacer exactamente esto en `T3_Modded.exe`**: agregar soporte real para `BulletHitPlasmaBlue.dat` como tercera tabla y reservarla inicialmente para `subType 1 / Weapon_Wm20`. Así tu archivo nuevo queda independiente y no tenemos que sacrificar ni alterar los impactos rojos de RSB80, FK, WM25, etc.

Si querés, el siguiente paso puede ser que **localice en `T3.exe` la función exacta `cSceneTask::BulletHit` y la condición que decide normal/plasma**, aprovechando además que tenemos `T3.pdb`. Con eso podemos determinar el parche binario concreto que tendría que aplicar nuestro `T3_Modded.exe`.

## Usuario · 2026-08-03 11:45:50

bueno, localiza eso y veamos si funciona el parche.

## ChatGPT · actualización

Voy a localizar la función de impacto usando las referencias a `BulletHitPlasma.dat`, los símbolos del PDB y el flujo que consume el `subType`. Después aplicaré un parche mínimo sobre una copia del ejecutable y te dejaré el binario modificado para probar, junto con qué archivos DAT debe contener el mod.

## ChatGPT · actualización

El PDB trae símbolos útiles (`cSceneTask::BulletHit`, `cBulletHit::AddNew`, `cBulletHits::AddNew`), así que podemos trabajar con nombres reales en vez de adivinar funciones. También confirma que el sistema de impacto está separado del render del proyectil; ahora estoy relacionando esos símbolos con direcciones del EXE y la tabla de 24 impactos.

## ChatGPT · actualización

Ya encontré el símbolo exacto, no sólo una referencia: `cSceneTask::BulletHit` está en el módulo `cSceneTask.obj`, stream 18 del PDB. El PDB le da offset `0x000F9D00` en la sección de código, que corresponde a **VA `0x004FAD00`**, y además indica una función muy corta (~`0x82` bytes), ideal para parchear con poco riesgo.

## ChatGPT · actualización

Encontré el punto que realmente decide el efecto visual: no es `cSceneTask::BulletHit` directamente, sino las llamadas posteriores a `cBulletHit::AddNew(PlayerIndex, BulletHitType, Position, Direction)`. Hay cinco call-sites juntos alrededor de `0x004F5082-0x004F54F7`; ahí debería aparecer la suma/selección entre los 12 impactos normales y los 12 plasma.

## ChatGPT · actualización

La condición quedó identificada con precisión: en `0x004F4FB1` el juego lee el subtipo del arma (`[esi+0x48]`). La lista que trata como plasma es `0, 1, 11, 12, 15, 16, 18, 19`, y en `0x004F4FDF` asigna `EBX = 12`; luego suma el tipo de superficie (0-11). **WM20 es exactamente el caso `subType == 1`.**

El obstáculo real es que `cBulletHit` tiene almacenamiento fijo para **24 configuraciones**, no 36: el propio `Init` reserva/recorre exactamente `0x18` entradas y las tablas de parámetros también están dimensionadas a 24. Estoy buscando la forma menos invasiva de añadir el azul sin pisar los impactos normales o los plasma rojos.

## ChatGPT · actualización

Al comparar los DAT hay otra pista útil: `BulletHitPlasma.dat` no sólo cambia una textura; también cambia tamaños, tiempos, velocidad, cantidad de partículas y color según superficie. Por eso un parche que sólo cambie `Muzzle-Front-Plasma.tga` sería incompleto. Voy a preparar primero un **parche de prueba aislado** que demuestra que podemos separar WM20 del resto; después, si arranca y el impacto cambia correctamente, extendemos la carga real del tercer DAT sin tocar las armas de bala.

## ChatGPT · actualización

Ya tengo un parche de diagnóstico viable que no requiere agrandar todavía la estructura de 24 slots: **saco únicamente `subType 1` (WM20) de la familia plasma y hago que esa familia alternativa cargue tu `Particles/BulletHitPlasmaBlue.dat`**. Tiene una limitación deliberada para esta primera prueba: las armas balísticas normales también usarán ese DAT azul. Si WM20 cambia a azul y los otros plasmas siguen rojos, habremos validado los dos puntos críticos del parche antes de implementar el tercer banco real.

## ChatGPT · actualización

El ejecutable de diagnóstico ya está construido y la estructura PE quedó válida: añadí una sección `.t3blue` que contiene literalmente `Particles/BulletHitPlasmaBlue.dat`, y el branch de WM20 quedó parcheado en **VA `0x004F4FBB`**. También hice una variante “route only” para separar si falla la selección de WM20 o si falla la carga del DAT.

## ChatGPT

Sí. Localicé la lógica y preparé un parche de prueba.

El hallazgo principal es que `cSceneTask::BulletHit` está en **`0x004FAD00`**, pero la selección real entre impacto normal/plasma ocurre antes, en:

```text
004F4FB1 mov eax,[esi+48h] ; weapon subtype
004F4FB4 test eax,eax
004F4FB6 je plasma
004F4FB8 cmp eax,1 ; <-- WM20
004F4FBB je plasma ; <-- branch que parcheamos
...
004F4FDF mov ebx,0Ch ; banco plasma = 12
```

Así que quedó confirmado que **`subType 1` identifica al WM20 en esta decisión**.

También confirmé:

```text
cBulletHit::Init = 0x004BA6C0
cBulletHit::AddNew = 0x004BC3D0
cSceneTask::BulletHit = 0x004FAD00
```

Y `cBulletHit::Init` tiene almacenamiento fijo para:

```text
0-11 BulletHit.dat
12-23 BulletHitPlasma.dat
```

Es decir, **24 configuraciones exactas**. Por eso no podemos todavía hacer simplemente `24-35 = Blue`: corrompería memoria.

### Parche de diagnóstico

Preparé dos ejecutables.

[Archivo generado: T3_WM20_BlueDAT_Diagnostic.exe]

Este hace:

```text
WM20 / subtype 1
        ↓
banco 0
        ↓
Particles/BulletHitPlasmaBlue.dat
```

```text
otros plasma
        ↓
banco 12
        ↓
Particles/BulletHitPlasma.dat
```

La ruta `Particles/BulletHitPlasmaBlue.dat` está agregada literalmente al EXE mediante una nueva sección PE `.t3blue`.

**Limitación intencional de esta primera prueba:** las armas balísticas normales también usan banco 0, por lo que también van a leer `BulletHitPlasmaBlue.dat`. No es el parche final; sirve para comprobar que WM20 puede separarse de los demás plasma y que el juego acepta tu nuevo DAT.

También hice esta variante:

[Archivo generado: T3_WM20_NormalRoute_Test.exe]

Esta sólo modifica:

```text
004F4FBB
74 22 ; JE plasma
```

por:

```text
90 90 ; NOP NOP
```

Así WM20 pasa a usar `BulletHit.dat`, sin tocar cómo se cargan los DAT. Es útil para diagnosticar si el primer parche falla.

### Para tu `T3_Modded.exe`

Como los EXE de arriba están construidos sobre el `T3.exe` original del ZIP, también hice un parcheador que busca las instrucciones por patrón. Podés aplicarlo directamente a **tu actual `T3_Modded.exe`**, así conservás el soporte de `Mods.Cod`:

[Archivo generado: patch_wm20_blue_diagnostic.py]

En Windows:

```text
py patch_wm20_blue_diagnostic.py T3_Modded.exe T3_Modded
```

Generará:

```text
T3_Modded_WM20_NormalRoute_Test.exe
T3_Modded_WM20_BlueDAT_Diagnostic.exe
```

El script comprueba los patrones antes de modificar nada; si tu `T3_Modded.exe` difiere demasiado, aborta en vez de parchear una dirección equivocada.

### Qué probar

Incluí tu archivo exactamente como:

```text
Particles/BulletHitPlasmaBlue.dat
```

y ejecutá preferentemente:

```text
T3_Modded_WM20_BlueDAT_Diagnostic.exe
```

Probá:

1. **WM20** -> debería usar `BulletHitPlasmaBlue.dat`.

2. **RSB80** -> debería continuar con `BulletHitPlasma.dat`.

3. **FK0** -> debería continuar con `BulletHitPlasma.dat`.

4. Una pistola/rifle convencional -> por ahora también debería mostrar el Blue DAT; es la limitación conocida del diagnóstico.

Si obtenemos exactamente ese comportamiento, queda demostrado que **la separación de WM20 funciona**. El siguiente parche ya sería el interesante: darle a `cBulletHit` un **tercer banco real Blue** sin modificar absolutamente nada de los impactos balísticos.

También te dejo el análisis técnico:

[Archivo generado: WM20_BLUE_PATCH_README.txt]

No puedo ejecutar T3 gráficamente en este entorno, así que validé el PE, las instrucciones modificadas, las referencias y la nueva sección, pero la prueba definitiva del efecto visual hay que hacerla in-game.

## Usuario · 2026-08-03 12:21:25

si ejecutar "patch_wm20_blue_diagnostic.py" en T3/ me deberia generar los dos .exe en el directorio del juego, no me estan apareciendo.

## ChatGPT · actualización

Sí: si lo ejecutás desde `T3/` y el script encuentra `T3_Modded.exe`, debería dejar ahí mismo los dos ejecutables generados. Voy a revisar el script que te pasé porque probablemente está esperando argumentos obligatorios o está escribiendo en otro directorio según cómo se lo ejecute.

## ChatGPT

El problema es que el script anterior **requería que le pasaras el EXE como argumento**. Si ejecutabas simplemente:

```text
py patch_wm20_blue_diagnostic.py
```

mostraba el `Usage` y terminaba sin generar nada.

La forma correcta con el script anterior era:

```text
cd C:\ruta\a\T3
py patch_wm20_blue_diagnostic.py T3_Modded.exe
```

y entonces debía crear en esa misma carpeta:

```text
T3_Modded_WM20_NormalRoute_Test.exe
T3_Modded_WM20_BlueDAT_Diagnostic.exe
```

Para hacerlo más cómodo, corregí el script para que **detecte automáticamente `T3_Modded.exe` o `T3.exe` en la misma carpeta**.

[Archivo generado: patch_wm20_blue_diagnostic_autodetect.py]

Ponelo dentro de:

```text
T3/
```

junto a:

```text
T3_Modded.exe
```

y ejecutá simplemente:

```text
py patch_wm20_blue_diagnostic_autodetect.py
```

Ahora debería mostrar algo parecido a:

```text
Using input: C:\...\T3\T3_Modded.exe
Input SHA256: ...
```

```text
Created: C:\...\T3\T3_Modded_WM20_NormalRoute_Test.exe
Created: C:\...\T3\T3_Modded_WM20_BlueDAT_Diagnostic.exe
```

```text
Done. Both EXEs were written next to the input executable.
```

Además, si algo falla ahora **te va a mostrar el error concreto** en vez de simplemente no generar los archivos.

Para esta prueba usaría primero:

```text
T3_Modded_WM20_BlueDAT_Diagnostic.exe
```

con tu:

```text
Particles/BulletHitPlasmaBlue.dat
```

incluido en el mod.

## Usuario · 2026-08-03 12:43:43

T3_Modded_WM20_BlueDAT_Diagnostic.exe crashea con lo siguiente; "====================================== =============== Exception code: C0000005 ACCESS_VIOLATION Fault address: 00510BF3 01:0010FBF3 D:\Program Files\T3\T3_Modded_WM20_BlueDAT_Diagnostic.exe ====================================== ===============

The report file generated on your computer: 'D:\Program Files\T3\T3_Modded_WM20_BlueDAT_Diagnostic.RPT" y reabre el juego sin efectos en el gameplay: T3_Modded_WM20_NormalRoute_Test.exe crashea y reabre el juego y no vuelve a crashear una vez se reabre; el normalroute exe produce algo Muzzle-Front-Plasma-Blue.tga no es leido y en su lugar no tiene textura pero es una modificacion. me olvide de pasarte donde tengo el dat que hace el mod, tal vez por eso no tiene textura ; T3\mods\T3 - Enhanced SFX\files\Particles\BulletHitPlasmaBlue.dat las texturas mod estan en T3\mods\T3 - Enhanced SFX\files\Textures\Particles

## ChatGPT · actualización

Esto ayuda mucho: el `NormalRoute` demuestra que **la bifurcación por `subType == 1` sí está funcionando**. El crash del `BlueDAT_Diagnostic` apunta más bien a cómo añadí la nueva cadena/sección al PE, no a la lógica de WM20.

También hay una segunda cuestión: tu `BulletHitPlasmaBlue.dat` está dentro de `mods\T3 - Enhanced SFX\files\...`, así que el ejecutable no lo ve directamente; primero tiene que quedar incluido en `Mods.Cod` por el compilador del mod. Voy a revisar ambas cosas por separado.

## ChatGPT · actualización

El `0x00510BF3` del crash no pertenece al código que parcheamos; es una rutina de inicialización/destrucción que intenta leer un objeto inválido (`[esi+0x2A94C]`). Eso encaja con que **alterar la tabla de secciones del PE está desestabilizando el arranque/reinicio**, mientras que el `NormalRoute` (que sólo cambia 2 bytes) llega a funcionar.

Voy a quitar por completo la sección `.t3blue`: podemos guardar la ruta nueva dentro de espacio ya mapeado del EXE y así el tamaño/estructura del ejecutable queda idéntico al original.

## ChatGPT · actualización

Hay una explicación concreta para lo que viste con `NormalRoute`: ese EXE **no busca `BulletHitPlasmaBlue.dat`**. Sólo manda WM20 al banco normal, que sigue cargando `Particles/BulletHit.dat`. Por eso tu archivo azul en `mods\T3 - Enhanced SFX\files\Particles\BulletHitPlasmaBlue.dat` queda fuera de esa prueba.

La prueba correcta, sin tocar la tabla PE, es temporalmente hacer que tu `BulletHitPlasmaBlue.dat` también exista en el mod como `Particles\BulletHit.dat`. Así WM20 leerá el contenido azul por el banco normal, mientras RSB80/FK seguirán usando `BulletHitPlasma.dat`.

## ChatGPT · actualización

Para eliminar también la duda de la textura, voy a añadir un verificador de `Mods.Cod`. Así después de recompilar podemos confirmar en segundos si el archivo azul y `Muzzle-Front-Plasma-Blue.tga` realmente quedaron empaquetados; si no están ahí, el engine jamás podrá encontrarlos aunque el parche sea correcto.

## ChatGPT

Sí, con lo que me pasaste ya podemos corregir la prueba. Hay dos problemas distintos.

El `BlueDAT_Diagnostic` que hice antes no es fiable: añadía una sección nueva `.t3blue` al PE, y el crash en `0x00510BF3` ocurre fuera de nuestra lógica de impactos. Lo descarto. Además, ejecutar copias con nombres como `T3_Modded_WM20_...exe` introduce otra variable en el sistema de recuperación/reinicio del juego.

La prueba nueva **no añade secciones, no cambia rutas internas y no crea otro EXE**. Parchea tu `T3_Modded.exe` actual en el mismo sitio, haciendo backup antes.

### Qué vamos a probar

Sabemos que originalmente:

```text
WM20
subType 1
   ↓
plasma
   ↓
BulletHitPlasma.dat
```

El parche de sólo 2 bytes cambia exclusivamente WM20 a:

```text
WM20
subType 1
   ↓
normal bank
   ↓
BulletHit.dat
```

Entonces, temporalmente vamos a poner **el contenido de tu `BulletHitPlasmaBlue.dat` bajo el nombre `BulletHit.dat`** dentro del mod:

```text
T3\mods\T3 - Enhanced SFX\files\Particles\
    BulletHitPlasmaBlue.dat ← tu archivo original
    BulletHit.dat ← copia temporal del anterior
```

Así no necesitamos enseñarle al engine un nombre de archivo nuevo todavía.

[Archivo generado: prepare_wm20_blue_test.py]

Ponelo directamente en:

```text
T3\
```

donde están:

```text
T3_Modded.exe
mods\
Game.cod
...
```

y ejecutá:

```text
py prepare_wm20_blue_test.py
```

El script:

```text
1. Busca T3_Modded.exe
2. Crea:
   T3_Modded.before_WM20_blue_test.exe
```

```text
3. Parchea T3_Modded.exe EN EL MISMO ARCHIVO:
   WM20 subtype 1 -> banco normal
```

```text
4. Busca:
   mods\T3 - Enhanced SFX\files\Particles\
   BulletHitPlasmaBlue.dat
```

```text
5. Lo copia como:
   BulletHit.dat
```

```text
6. Si ya tenías un BulletHit.dat modificado, lo preserva como:
   BulletHit.before_WM20_blue_test.dat
```

```text
7. También revisa las referencias .tga que encuentre dentro del DAT.
```

Después **tenés que volver a compilar/actualizar `Mods.Cod`** con el Asset Tool. Esto es importante: simplemente tener:

```text
mods\T3 - Enhanced SFX\files\Textures\Particles\
```

no significa que el juego ya lo esté leyendo; esos archivos tienen que terminar dentro del `Mods.Cod` que carga `T3_Modded.exe`.

Luego ejecutá el mismo:

```text
T3_Modded.exe
```

No un `T3_Modded_WM20_....exe`.

### Qué debería ocurrir

Si nuestra identificación de la lógica es correcta:

```text
WM20
 -> BulletHit.dat
 -> que temporalmente contiene BulletHitPlasmaBlue.dat
 -> IMPACTOS AZULES
```

```text
RSB80
 -> BulletHitPlasma.dat
 -> continúa ROJO
```

```text
FK0
 -> BulletHitPlasma.dat
 -> continúa ROJO
```

Durante esta prueba hay una limitación:

```text
Armas balísticas normales
 -> también usan BulletHit.dat
 -> también van a tener el efecto azul
```

Eso es intencional. Lo único que estamos verificando ahora es:

**¿Podemos sacar WM20 del banco plasma rojo sin afectar RSB80/FK?**

Si la respuesta es sí, después construimos el tercer banco real.

### Sobre `Muzzle-Front-Plasma-Blue.tga`

Tu ubicación:

```text
T3\mods\T3 - Enhanced SFX\files\Textures\Particles\
```

es correcta **si dentro del DAT la referencia es**, por ejemplo:

```text
Textures\Particles\Muzzle-Front-Plasma-Blue.tga
```

El archivo debería estar exactamente en:

```text
T3\mods\T3 - Enhanced SFX\files\
    Textures\
        Particles\
            Muzzle-Front-Plasma-Blue.tga
```

El script nuevo también intenta comprobar esto.

Además hice un segundo script para revisar directamente el `Mods.Cod` resultante:

[Archivo generado: check_wm20_blue_mods_cod.py]

Después de compilar el mod:

```text
py check_wm20_blue_mods_cod.py
```

Debería decir:

```text
[FOUND] Particles/BulletHit.dat
[FOUND] Particles/BulletHitPlasmaBlue.dat
[FOUND] Textures/Particles/Muzzle-Front-Plasma-Blue.tga
```

En realidad, para esta prueba los dos imprescindibles son:

```text
Particles/BulletHit.dat
Textures/Particles/Muzzle-Front-Plasma-Blue.tga
```

porque `BulletHitPlasmaBlue.dat` bajo su nombre nuevo todavía no es leído directamente por el juego.

También te dejo el restaurador:

[Archivo generado: restore_wm20_blue_test.py]

Ejecutándolo desde `T3\`:

```text
py restore_wm20_blue_test.py
```

restaura el `T3_Modded.exe` previo y tu `BulletHit.dat` anterior si existía. Después hay que reconstruir nuevamente `Mods.Cod`.

El resultado que más nos interesa ahora es muy específico: **WM20 azul + RSB80 rojo + FK rojo**. Si obtenemos eso, ya no hay que investigar más la clasificación del arma: queda demostrada. El siguiente trabajo sería darle a WM20 almacenamiento propio para una tercera tabla `BulletHitPlasmaBlue.dat`, sin compartirla con las armas balísticas.

## Usuario · 2026-08-03 13:04:01

en el juego las balas del wm20 se ven Azules ahora que esta bien. pero al poner BulletHitPlasmaBlue.dat bajo el nombre BulletHit.dat tambien se estan viendo los impactos de balas normales en azul. Esto sucede por que los impactos de balas plasma originales estan en BulletHitPlasma.dat no en BulletHit.dat Asi que tendriamos que apuntar a testear modificar ese. El BulletHit.dat lo he quitado de mi mod ya que no es el .dat que hay que tocar.

## ChatGPT · actualización

Exacto: quitar `BulletHit.dat` del mod fue lo correcto. La prueba anterior confirmó solamente que podemos separar al WM20 por `subType == 1`, pero usó el banco equivocado como destino.

Ahora el objetivo correcto es más específico: **mantener `BulletHit.dat` intacto para balas normales, mantener `BulletHitPlasma.dat` rojo para los demás plasma y hacer que sólo WM20 use `BulletHitPlasmaBlue.dat`**. Voy a trabajar sobre la carga del segundo banco, no sobre el banco normal.

## ChatGPT · actualización

Hay una forma de probar esto sin tocar `BulletHit.dat` ni agrandar todavía la estructura: **reservar temporalmente una sola entrada del banco `BulletHitPlasma.dat` para WM20** y forzar al WM20 a usar siempre esa entrada, sin importar la superficie.

No sería el parche final porque perderíamos diferencias por material para WM20 durante la prueba, pero sí nos permitiría verificar exactamente lo que necesitamos: balas normales intactas, plasma rojo intacto, y WM20 azul usando el banco plasma. Estoy localizando qué slot conviene sacrificar temporalmente y dónde forzar ese índice.

## ChatGPT · actualización

Sí, exactamente. El próximo test debe usar **el banco plasma real**, no `BulletHit.dat`: restauramos el branch de WM20 para que vuelva a `EBX = 12` y temporalmente hacemos que `BulletHitPlasma.dat` contenga tu versión azul.

El resultado esperado de esa prueba será: **balas normales normales; WM20 azul; RSB80/FK y demás plasma también azules**. Todavía no aísla WM20, pero confirma que `BulletHitPlasmaBlue.dat` y sus texturas funcionan correctamente dentro del banco que realmente corresponde.

## ChatGPT

Sí, tu interpretación es correcta. `BulletHit.dat` no debe formar parte de esta prueba.

Lo que acabamos de demostrar fue sólo que el branch de `WM20 / subType 1` puede cambiarse. Ahora hay que probarlo dentro de su banco correcto: **`BulletHitPlasma.dat`**.

Preparé este script:

[Archivo generado: prepare_wm20_correct_plasma_bank_test.py]

Ponelo en `T3\` y ejecutá:

```text
py prepare_wm20_correct_plasma_bank_test.py
```

Hace dos cosas:

```text
1. Restaura T3_Modded.exe:
   WM20 subType 1 -> banco plasma
   90 90 -> 74 22
```

```text
2. Copia temporalmente:
   BulletHitPlasmaBlue.dat
        ↓
   BulletHitPlasma.dat
```

Usando exactamente tu ubicación:

```text
T3\mods\T3 - Enhanced SFX\files\Particles\
    BulletHitPlasmaBlue.dat
```

y crea:

```text
T3\mods\T3 - Enhanced SFX\files\Particles\
    BulletHitPlasma.dat
```

Después recompilá/actualizá `Mods.Cod` y arrancá **el mismo `T3_Modded.exe`**.

El resultado esperado ahora es:

```text
Armas de bala normales
    ↓
BulletHit.dat
    ↓
NORMALES / sin cambios
```

```text
WM20
    ↓
BulletHitPlasma.dat
    ↓
AZUL
```

```text
RSB80
    ↓
BulletHitPlasma.dat
    ↓
AZUL
```

```text
FK0
    ↓
BulletHitPlasma.dat
    ↓
AZUL
```

Que RSB80 y FK también queden azules en este test es intencional. Lo que queremos comprobar ahora es que **tu DAT azul y `Muzzle-Front-Plasma-Blue.tga` funcionan correctamente cuando están cargados en el banco plasma verdadero**.

No agregues:

```text
Particles\BulletHit.dat
```

al mod para esta prueba.

También dejé un restaurador:

[Archivo generado: restore_plasma_bank_test.py]

Después del test:

```text
py restore_plasma_bank_test.py
```

y recompilás nuevamente `Mods.Cod`.

Si el resultado es **balas normales intactas + todos los plasma azules**, entonces ya quedan confirmadas las dos piezas por separado:

```text
  Podemos identificar WM20 por subType 1
  BulletHitPlasmaBlue funciona correctamente como banco plasma
```

Y ahí sí el siguiente parche tiene un objetivo perfectamente definido: crear para WM20 un **tercer banco independiente**, en vez de seguir reutilizando `BulletHit.dat` o sobrescribiendo globalmente `BulletHitPlasma.dat`.

## Usuario · 2026-08-03 13:14:35

Bueno, ahora si bien los impactos del fusil plasma WM20 se ven azules hay otras armas plasma en el juego y las otras como tienen lasers rojos deberian tener impactos en color rojo osea el color que usarian por defecto pero fueron afectados sus colores impactos tambien ya que toman la textura del BulletHitPlasma.dat. Para que no pase esto cree el BulletHitPlasmaBlue.dat, asi no se reemplaza el contenido original del BulletHitPlasma.dat.

## ChatGPT · actualización

Exactamente. Ese es el comportamiento final que necesitamos: **no tocar `BulletHit.dat` ni reemplazar `BulletHitPlasma.dat`**. `BulletHitPlasmaBlue.dat` tiene que cargarse como un recurso adicional y sólo `WM20 / subType 1` debe apuntar a él.

Las dos pruebas anteriores ya validaron por separado que el WM20 se puede identificar y que tu DAT azul funciona. Ahora voy a atacar el punto que falta: ampliar la inicialización de `cBulletHit` para que cargue un tercer banco sin afectar los 24 slots originales.

## ChatGPT · actualización

Hay un detalle estructural importante que explica por qué no alcanza con “cambiar la ruta”: `cBulletHit` está embebido dentro de `cSceneTask` y ocupa exactamente **0x2814 bytes**. Justo después empieza otro objeto del engine, así que escribir slots 24-35 “a continuación” destruiría memoria del siguiente sistema y produciría otro `ACCESS_VIOLATION`.

La salida correcta será cargar el banco azul en memoria separada y hacer que sólo la creación de impactos del WM20 consulte esos datos. Estoy comprobando cuánto del DAT necesitamos duplicar para no tener que mover toda la estructura de escena.

## ChatGPT · actualización

Ya encontré una alternativa bastante más limpia que agrandar `cSceneTask`: crear **un segundo objeto `cBulletHit` completo en memoria dinámica**. El original conserva sus 24 slots (`BulletHit.dat` + `BulletHitPlasma.dat`) y el segundo carga `BulletHit.dat` + `BulletHitPlasmaBlue.dat`.

Luego podemos marcar internamente los impactos de WM20 como tipos `24-35`; un wrapper los redirige al segundo objeto y los convierte otra vez en `12-23` antes de llamar a `cBulletHit::AddNew`. Así conservamos también las 12 variantes por superficie, no sólo un único impacto azul genérico.

## ChatGPT · actualización

La lógica ya está armada de forma que **`BulletHitPlasma.dat` no se modifica**. También encontré todas las llamadas que hay que duplicar para el segundo `cBulletHit`: `Init`, `Draw`, `SettingsChanged`, `Done` y los cinco `AddNew`.

Estoy empaquetando esto como parcheador del `T3_Modded.exe` actual, usando espacio libre ya existente dentro del PE -sin añadir secciones nuevas- para evitar el tipo de crash que produjo el primer diagnóstico.

## ChatGPT

Exactamente. El parche correcto tiene que mantener **tres bancos independientes**, sin reemplazar ninguno:

```text
Armas balísticas
    ↓
BulletHit.dat
    ↓
impactos normales
```

```text
RSB80 / FK / demás plasma rojo
    ↓
BulletHitPlasma.dat
    ↓
impactos rojos originales
```

```text
WM20 / subType 1
    ↓
```

```text
BulletHitPlasmaBlue.dat
    ↓
impactos azules
```

Preparé ahora un parche experimental que hace realmente eso:

[Archivo generado: patch_wm20_true_blue_bank.py]

### Qué cambia técnicamente

El problema era que `cBulletHit` sólo tiene físicamente 24 slots:

```text
0-11 BulletHit.dat
12-23 BulletHitPlasma.dat
```

Y justo después de esos datos empieza otro objeto del engine. No podemos simplemente escribir `24-35` allí.

El parche nuevo hace algo diferente: crea **un segundo `cBulletHit` de 0x2814 bytes en memoria dinámica**.

Queda así:

```text
cBulletHit original
├─ 0-11 BulletHit.dat
└─ 12-23 BulletHitPlasma.dat
```

```text
cBulletHit BLUE
├─ 0-11 BulletHit.dat ← prácticamente no usado
└─ 12-23 BulletHitPlasmaBlue.dat
```

Cuando el juego detecta:

```text
weapon subType == 1
```

que es WM20, internamente le asignamos:

```text
24-35
```

Luego interceptamos `cBulletHit::AddNew` y hacemos:

```text
24-35
   ↓
usar cBulletHit BLUE
   ↓
convertir a 12-23
```

Por eso conserva incluso las **12 variantes según superficie** de tu `BulletHitPlasmaBlue.dat`.

### Además

El segundo `cBulletHit` también recibe sus llamadas correspondientes de:

```text
Init
AddNew
Draw
SettingsChanged
Done
```

Así que no es simplemente cambiar una textura en memoria.

Y esta vez **no agrego una sección nueva al PE**. El código usa padding ya existente de `.text` y `.data1`, evitando el enfoque que produjo aquel `ACCESS_VIOLATION`.

### Cómo probarlo

Dejá:

```text
T3\mods\T3 - Enhanced SFX\files\Particles\
    BulletHitPlasmaBlue.dat
```

y tus texturas:

```text
T3\mods\T3 - Enhanced SFX\files\Textures\Particles\
    Muzzle-Front-Plasma-Blue.tga
    ...
```

No pongas una copia azul como:

```text
BulletHit.dat
```

ni como:

```text
BulletHitPlasma.dat
```

`BulletHitPlasma.dat` debe seguir siendo el rojo original.

Poné el script en:

```text
T3\
```

y ejecutá:

```text
py patch_wm20_true_blue_bank.py
```

El script parchea **el mismo**:

```text
T3_Modded.exe
```

y crea antes un backup:

```text
T3_Modded.before_WM20_true_blue_bank.exe
```

Después recompilá/actualizá `Mods.Cod` con el Asset Tool y ejecutá:

```text
T3_Modded.exe
```

### Resultado que buscamos

```text
WM20
→ láser azul
→ impactos AZULES
```

```text
RSB80
→ láser rojo
→ impactos ROJOS
```

```text
FK
→ láser rojo
→ impactos ROJOS
```

```text
armas convencionales
→ impactos normales
```

El parcheador además detecta restos de nuestras pruebas anteriores. Si `BulletHitPlasma.dat` era simplemente una copia temporal idéntica de `BulletHitPlasmaBlue.dat`, la elimina; si existía un backup del DAT rojo previo, lo restaura.

También te dejo el restaurador:

[Archivo generado: restore_wm20_true_blue_bank.py]

Y la explicación técnica:

[Archivo generado: WM20_TRUE_BLUE_BANK_README.txt]

Validé el código inyectado, los saltos, las cinco llamadas a `AddNew`, la estructura PE y la ruta nueva. La prueba que realmente importa ahora es arrancar el juego y comprobar **WM20 azul mientras RSB80/FK permanecen rojos**.

## Usuario · 2026-08-03 13:54:29

perfecto funciona bien, me olvide avisar, me gustaria que Weapon_termcannon tenga impacto azul igualmente ya que esa es otra arma con laser azul.

## ChatGPT · actualización

Perfecto. Voy a localizar el `subType` exacto de `Weapon_termcannon` y luego adaptar el parche para que **WM20 y termcannon** se redirijan al banco `BulletHitPlasmaBlue.dat`, manteniendo el resto del plasma en rojo.

## ChatGPT · actualización

Encontré el dato clave: **Termcannon es `subType 15`**, y es el único `weapon1.option` del juego que usa ese subtipo:

```text
weapons/Termcannon/weapon1.option
type granade
```

```text
subType 15
```

Además, `15` ya estaba dentro de la lista que el engine clasifica como plasma rojo. Así que no necesitamos otro banco ni tocar `BulletHitPlasmaBlue.dat`: basta con ampliar nuestro selector azul de **`subType == 1` (WM20)** a **`subType == 1 || subType == 15` (Termcannon)**.

## ChatGPT · actualización

Como ya tenés el parche funcionando, lo más seguro es **no reinstalar todo**. Voy a hacer un actualizador mínimo que sólo modifica el hook azul existente: conserva el segundo `cBulletHit`, las rutas y todos los demás cambios, y añade `subType 15` a la misma condición azul.

## ChatGPT

Perfecto. Confirmé que **Termcannon usa exclusivamente `subType 15`**, así que podemos añadirlo al mismo banco azul del WM20 sin afectar las demás armas plasma:

```text
WM20 subType 1 → BulletHitPlasmaBlue.dat
Termcannon subType 15 → BulletHitPlasmaBlue.dat
```

```text
RSB80 / FK / demás plasma → BulletHitPlasma.dat
Balas normales → BulletHit.dat
```

Como ya tenés funcionando el parche anterior, preparé un **actualizador mínimo** que sólo modifica esa condición existente.

[Archivo generado: update_termcannon_blue_impact.py]

Ponelo en `T3\` junto a `T3_Modded.exe` y ejecutá:

```text
py update_termcannon_blue_impact.py
```

El script crea primero:

```text
T3_Modded.before_Termcannon_blue.exe
```

y cambia la condición internamente de:

```text
if (subType == 1)
    useBlueImpact();
```

a:

```text
if (subType == 1 || subType == 15)
    useBlueImpact();
```

No crea otro `cBulletHit`, no duplica memoria y no toca `BulletHitPlasma.dat`: **Termcannon simplemente comparte el banco azul que ya funciona con WM20**.

Si tu actual `Mods.Cod` ya contiene:

```text
Particles/BulletHitPlasmaBlue.dat
```

y sus texturas azules, **no hace falta recompilar el mod**. Sólo ejecutar el script y arrancar `T3_Modded.exe`.

También hice un restaurador por si fuera necesario:

[Archivo generado: restore_termcannon_blue_update.py]

El resultado final debería ser:

```text
WM20
  → impacto azul
```

```text
Weapon_TermCannon
  → impacto azul
```

```text
RSB80
  → impacto rojo
```

```text
FK
  → impacto rojo
```

```text
WM25 / demás plasma rojo
  → impacto rojo
```

Probé el actualizador sobre un `T3_Modded.exe` con nuestro parche anterior instalado y reconoce/modifica correctamente el hook existente.

## Usuario · 2026-08-09 01:11:22

dame un pdf de este chat
