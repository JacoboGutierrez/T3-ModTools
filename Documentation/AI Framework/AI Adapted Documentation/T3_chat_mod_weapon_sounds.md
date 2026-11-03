# T3 Modding - Chat sobre sonidos de armas

Conversacion exportada a PDF - problema: los disparos automaticos reinician/cortan su propio sonido.

## Usuario

Tuve una idea de un mod simple. actualmente los disparos de todas las armas tienen algo poco realista, al disparar los sonidos se pisan entre si, es decir por ejemplo una ametralladora dispara y el sonido es cortado y reproducido de 0 por el nuevo disparo, hay alguna forma en la que podamos modear esto de tal forma que el sonido se termine de reproducir incluso cuando ya se esta disparando otra bala o cualquiera sea el proyectil?

## ChatGPT

Si, es posible, pero probablemente no sea un cambio de audio sino del sistema que reproduce los sonidos.

Lo que parece estar ocurriendo es que cada arma reutiliza una unica "voz" o canal de audio:

1. Se dispara una bala.

2. Comienza weapon_fire.wav.

3. Se dispara otra bala.

4. El juego reinicia ese mismo canal desde el segundo 0.

5. La cola del disparo anterior se corta.

El comportamiento que buscamos es polifonia: cada disparo debe utilizar una instancia de audio distinta, permitiendo que varias copias del mismo sonido se superpongan.

### Solucion ideal

En vez de algo equivalente a:

```text
weaponSound.stop();
weaponSound.play();
```

necesitariamos un pequeno pool de canales:

```text
shotSounds[nextChannel].play();
nextChannel = (nextChannel + 1) % MAX_SHOT_CHANNELS;
```

Por ejemplo, una ametralladora podria disponer de 6 u 8 instancias del sonido:

```text
Disparo 1 -> canal 1
Disparo 2 -> canal 2
Disparo 3 -> canal 3
Disparo 4 -> canal 4
...
```

Cuando se reutilice el primer canal, su sonido anterior normalmente ya habra terminado.

La cantidad necesaria puede calcularse aproximadamente asi:

```text
canales = duracion del sonido / tiempo entre disparos
```

Si el sonido dura 0,30 segundos y el arma dispara cada 0,08 segundos:

```text
0,30 / 0,08 = 3,75
```

Necesitariamos al menos 4 canales, aunque usaria entre 6 y 8 para dejar margen.

### Que tan sencillo seria en T3

Hay tres posibilidades:

1. Existe una propiedad en los archivos del juego

Podria haber parametros similares a:

MaxInstances

Concurrency

InterruptMode

AllowOverlap

```text
Channel
```

VoiceLimit

En ese caso, seria un mod relativamente sencillo dentro de los archivos .cod o de alguna definicion de armas/sonidos.

2. El sonido esta asociado a una entidad o evento reutilizado

Podriamos intentar hacer que cada proyectil, efecto de boca o entidad temporal reproduzca su propia copia del sonido. Asi cada disparo crearia una nueva fuente de audio sin modificar directamente el motor.

Este seria un buen punto intermedio y posiblemente podria hacerse con el sistema de mods actual.

3. El comportamiento esta programado dentro de T3.exe

En ese caso, haria falta modificar o interceptar el sistema de audio:

- localizar la funcion que reproduce los disparos;

- comprobar si detiene el sonido anterior;

- eliminar esa interrupcion;

- crear un pool de fuentes de audio;

- o interceptar las llamadas a DirectSound/OpenAL, dependiendo de la biblioteca utilizada.

Esto ya seria mas parecido a un engine patch o DLL loader que a un reemplazo normal de archivos.

### Riesgo adicional: volumen y saturacion

Superponer disparos hara que el sonido sea mas realista, pero tambien puede producir clipping. Conviene:

- bajar cada disparo entre 3 y 6 dB;

- limitar las instancias simultaneas;

- conservar prioridad para explosiones, voces y sonidos importantes;

- posiblemente separar el sonido en ataque y cola.

Una implementacion mas avanzada seria:

```text
shot_transient.wav -> se reproduce en cada bala
shot_tail.wav -> puede superponerse o reproducirse con menor frecuencia
```

Esto daria una rafaga mas natural sin acumular demasiados sonidos completos.

### Como investigaria primero

Haria una prueba con un arma automatica y otra semiautomatica para determinar:

- si el sonido se corta solamente al disparar la misma arma;

- si tambien se corta cuando otro personaje dispara;

- si dos enemigos usando la misma arma pueden producir sonidos simultaneos;

- si un disparo interrumpe unicamente su propio sonido o cualquier sonido del mismo archivo.

Esa prueba nos dira mucho:

- Si dos personajes pueden usar el mismo sonido simultaneamente, probablemente el limite sea por arma o entidad.

- Si todos se interrumpen entre si, probablemente haya una sola instancia global por archivo o evento.

- Si unicamente se corta el arma del jugador, puede estar implementado directamente en su controlador.

Por lo tanto, si: el mod es viable. Primero buscaria una propiedad de concurrencia en las definiciones extraidas. Si no existe, intentaria asociar el sonido al proyectil o al efecto de disparo. La modificacion del ejecutable quedaria como tercera opcion.

## Usuario

El sonido solo se corta si un jugador o npc dispara su arma automatica de forma individual, el npc se escucha cortada su propia arma y el jugador se escucha cortada su propia arma pero no por que disparen al mismo tiempo. Si un jugador y un npc estan disparando simultaneamente con la misma arma no se cortan el sonido entre ellos. el corte de sonido de disparos es individual. Nadie se interrumpe. Podrias buscar que causa esta interrupcion?

## ChatGPT

Si. Con el comportamiento que describiste, ya podemos reducir bastante la causa.

### Causa mas probable

Cada jugador o NPC parece tener una unica instancia de sonido asociada al arma equipada.

Al producirse un disparo, el juego probablemente ejecuta algo equivalente a:

```text
weaponFireSound->Stop();
weaponFireSound->SetPosition(0);
weaponFireSound->Play();
```

o simplemente:

```text
weaponFireSound->Play();
```

pero sobre un canal que ya esta ocupado. El sistema reinicia ese canal automaticamente.

Por eso sucede esto:

Jugador

nnn Arma

```text
nnn Canal de disparo unico
nnn disparo 1 comienza
nnn disparo 2 reinicia el canal
nnn disparo 3 vuelve a reiniciarlo
nnn nunca se escucha la cola completa
```

En cambio:

Jugador -- canal propio -- sonido A

NPC ----- canal propio -- sonido B

Los dos pueden disparar simultaneamente porque cada personaje posee su propio canal, aunque esten usando el mismo archivo de audio.

Esto practicamente descarta:

- un limite global por archivo de sonido;

- una sola instancia global para cada arma;

- falta general de canales del mezclador;

- que un NPC pueda robarle el sonido al jugador;

- que el problema este causado por el archivo WAV en si.

### Lo que pude verificar

T3 es un juego de 2003 que utiliza el entorno DirectX 9.0b y tiene un sistema de audio con inicializacion de tarjeta y soporte surround registrado en su log de depuracion. Eso apunta a un sistema de sonido tradicional del motor Clever's Technology, probablemente apoyado en una API de audio de la epoca. No encontre documentacion publica que revele la funcion concreta usada para los disparos.

Ademas, las criticas contemporaneas ya destacaban especificamente la mala implementacion de sonidos de ametralladoras y rifles, asi que no parece ser una anomalia de sistemas modernos, sino una limitacion original del juego.

No encontre en los archivos disponibles de nuestro proyecto definiciones de armas o del sistema de audio; actualmente aparecen principalmente herramientas y documentacion de modelos, LOD y animaciones. Por tanto, todavia no puedo senalar una linea exacta del juego, pero el patron permite ubicar con bastante precision donde buscar.

### Dos implementaciones posibles

1. Fuente de audio unica dentro del arma

Es la explicacion mas probable.

Cada instancia de arma tendria algo como:

```text
class Weapon {
SoundInstance* fireSound;
```

};

Cuando el arma dispara:

```text
fireSound->Play();
```

```text
La misma instancia vuelve a utilizarse en cada proyectil. Como fireSound pertenece al arma del
actor, otros personajes tienen sus propias instancias y no se interfieren.
```

La correccion seria crear una instancia nueva o utilizar un pool:

```text
class Weapon {
SoundInstance* fireSounds[8];
int nextFireSound;
```

};

```text
void PlayFireSound() {
fireSounds[nextFireSound]->SetPosition(0);
fireSounds[nextFireSound]->Play();
```

```text
nextFireSound = (nextFireSound + 1) % 8;
```

}

2. Emisor unico asociado al personaje

Tambien podria existir un emisor general por actor:

```text
actor->weaponSoundEmitter
```

Todos los disparos de ese actor utilizan el mismo emisor. No seria necesariamente exclusivo del arma; podria ser un canal como:

```text
VOICE
MOVEMENT
WEAPON
IMPACT
AMBIENT
```

```text
Cada disparo reemplazaria el sonido que este activo en el canal WEAPON.
```

En ese caso, el parche tendria que cambiar el disparo de un sonido "controlado" por el actor a un sonido one-shot independiente.

### Como encontrarlo exactamente

### Primero: identificar la biblioteca de audio

En la carpeta del juego hay que buscar:

```text
dsound.dll
mss32.dll
OpenAL32.dll
fmod.dll
fmodex.dll
```

Tambien se puede analizar T3.exe desde PowerShell:

```text
strings.exe T3.exe |
Select-String -Pattern `
"DirectSound|DirectSoundBuffer|dsound|AIL_|Miles|mss32|FMOD|OpenAL|alSourcePlay"
```

O con Visual Studio:

```text
dumpbin /imports T3.exe | findstr /i "dsound mss openal fmod"
```

Interpretacion:

```text
DSOUND.DLL -> DirectSound
DirectSoundCreate8 -> DirectSound 8
mss32.dll / AIL_* -> Miles Sound System
OpenAL32.dll / alSource* -> OpenAL
fmod*.dll -> FMOD
```

### Segundo: buscar configuraciones dentro de Game.cod

En todo lo extraido conviene buscar:

```text
Get-ChildItem "ruta\extraida" -Recurse -File |
Select-String -Pattern `
"FireSound|ShootSound|WeaponSound|SoundEmitter|SoundSource|Channel|Voice|Loop|Overlap|Interrupt|
Restart|OneShot|Polyphony|MaxInstances"
```

Tambien buscar directamente el nombre de un sonido de arma automatica:

```text
Get-ChildItem "ruta\extraida" -Recurse -File |
Select-String -SimpleMatch "nombre_del_disparo.wav"
```

Eso puede revelar la definicion que conecta:

```text
arma -> evento de disparo -> archivo de sonido
```

Si encontramos una definicion parecida a:

```text
FireSound "Weapons/ACW/fire.wav"
Loop 0
Channel WEAPON
```

```text
el campo sospechoso seria Channel. Si no existe ninguna propiedad de concurrencia, la
reutilizacion probablemente esta programada en T3.exe.
```

### Prueba especialmente util

Podemos reemplazar temporalmente el sonido de un arma automatica por un archivo que tenga:

0,05 s de disparo

0,50 s de silencio

0,20 s de tono claramente audible

Resultado esperado:

- Si el tono final nunca aparece durante una rafaga, pero aparece al soltar el gatillo, cada disparo esta reiniciando el mismo sample.

- Si el tono aparece una sola vez despues de soltar, es casi seguro que existe una unica instancia por arma.

- Si aparecen varios tonos superpuestos, entonces el corte percibido estaria incorporado en otro sample o en un sistema de loop.

Otra variante consiste en usar dos sonidos alternados:

```text
fire_A.wav -> tono grave al final
fire_B.wav -> tono agudo al final
```

Si el formato de armas admite varias variantes y aun asi se cortan, el limite esta en el emisor del actor, no en el recurso.

### Donde parchearia el ejecutable

Una vez identificada la API, habria que localizar llamadas repetidas al reproducir:

### DirectSound

Buscar importaciones o referencias a:

```text
IDirectSoundBuffer::Play
IDirectSoundBuffer::Stop
IDirectSoundBuffer::SetCurrentPosition
IDirectSound8::DuplicateSoundBuffer
```

El patron problematico seria:

```text
buffer->Stop();
buffer->SetCurrentPosition(0);
buffer->Play(0, 0, 0);
```

La solucion correcta en DirectSound seria crear buffers secundarios duplicados mediante DuplicateSoundBuffer y rotarlos.

### Miles Sound System

Buscar:

```text
AIL_allocate_sample_handle
AIL_init_sample
AIL_start_sample
AIL_end_sample
AIL_set_sample_file
```

El problema seria reutilizar siempre el mismo HSAMPLE almacenado en el arma. La solucion seria reservar varios handles.

### OpenAL

Buscar:

```text
alSourceStop
alSourceRewind
alSourcePlay
alSourcei
```

El error seria reutilizar un unico AL_SOURCE por arma. La correccion seria un pool de fuentes.

### Conclusion

La interrupcion es casi seguramente causada por la reutilizacion de una sola voz de audio por arma o por canal de arma del actor. Cada disparo reinicia esa voz; otros personajes no interfieren porque poseen otra instancia independiente.

```text
No parece solucionable reemplazando unicamente los sonidos. Puede existir una propiedad editable
dentro de las definiciones de armas, pero si no aparece algo como Channel, Overlap, MaxInstances
o OneShot, necesitaremos un pequeno parche para T3.exe o para la biblioteca de audio.
```

El siguiente paso concreto es analizar T3.exe, las DLL de su carpeta y una carpeta extraida de un arma automatica -por ejemplo ACW, SAW o minigun- para identificar si la correccion puede entrar en Mods.Cod o necesita incorporarse a T3_Modded.exe.
