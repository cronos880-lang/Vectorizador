# Actualizacion STL de prueba sobre instalacion existente de Vectorizador V2.6.
# Solo sustituye archivos de programa. No accede a Archivos, fotos, DXF, STL ni .vect.
param([string]$RutaInstalacion = "")
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$repo="cronos880-lang/Vectorizador"
$tag="stl-prueba-actualizacion-20261117"
$asset="Vectorizador_STL_Windows_Portable_Prueba.zip"
$download="https://github.com/$repo/releases/download/$tag/$asset"
$carpetaDatos=Join-Path $env:LOCALAPPDATA 'Vectorizador'
$copias=Join-Path $carpetaDatos 'Copias_actualizacion_STL'
$trabajo=Join-Path $env:TEMP ("Vectorizador_Update_STL_"+[Guid]::NewGuid().ToString('N'))
$temporalZip=Join-Path $trabajo $asset
$extraidos=Join-Path $trabajo 'Programa'
$instalado=$false
$completado=$false
$respaldados=New-Object System.Collections.ArrayList

function Obtener-Instalacion {
    $candidatos=New-Object System.Collections.ArrayList
    $claves=@(
      'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
      'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
      'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    foreach($clave in $claves){
        foreach($app in @(Get-ItemProperty -Path $clave -ErrorAction SilentlyContinue)){
            if($app.DisplayName -match '^Vectorizador\b' -and $app.InstallLocation){
                [void]$candidatos.Add([string]$app.InstallLocation)
            }
        }
    }
    foreach($ruta in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Vectorizador'),
        (Join-Path $env:ProgramFiles 'Vectorizador'),
        (Join-Path $env:LOCALAPPDATA 'Vectorizador'),
        'C:\Vectorizador'
    )){
        if($ruta){[void]$candidatos.Add($ruta)}
    }
    foreach($ruta in ($candidatos | Select-Object -Unique)){
        if(Test-Path -LiteralPath (Join-Path $ruta 'Vectorizador.exe')){
            return (Resolve-Path -LiteralPath $ruta).Path
        }
    }
    return ''
}

try {
    Write-Host '=== ACTUALIZACION STL DE PRUEBA - VECTORİZADOR V2.6 ===' -ForegroundColor Cyan
    Write-Host 'Los datos de %LOCALAPPDATA%\Vectorizador\Archivos no se modificaran.'
    if(!$RutaInstalacion){ $RutaInstalacion=Obtener-Instalacion }
    if($RutaInstalacion){
        Write-Host ("Instalacion localizada: "+$RutaInstalacion)
        $confirmacion=Read-Host 'Es la carpeta donde instalaste Vectorizador? (S/N)'
        if($confirmacion -notmatch '^[sS]$'){ $RutaInstalacion='' }
    }
    if(!$RutaInstalacion){
        $RutaInstalacion=Read-Host 'Escribe la CARPETA donde esta Vectorizador.exe (sin el nombre del EXE)'
        $RutaInstalacion=$RutaInstalacion.Trim('"')
    }
    if(!(Test-Path -LiteralPath (Join-Path $RutaInstalacion 'Vectorizador.exe') -PathType Leaf)){
        throw 'No se ha encontrado Vectorizador.exe. No se ha cambiado nada.'
    }
    $RutaInstalacion=(Resolve-Path -LiteralPath $RutaInstalacion).Path
    $activos=Get-Process -Name Vectorizador -ErrorAction SilentlyContinue
    if($activos){
        throw 'Vectorizador esta abierto. Cierra el icono V junto al reloj de Windows y repite la actualizacion.'
    }
    # No ejecutar una sustitucion parcial si no es posible escribir.
    $prueba=Join-Path $RutaInstalacion ('.comprobacion_STL_'+[Guid]::NewGuid().ToString('N'))
    try{
        [System.IO.File]::WriteAllText($prueba,'test')
    }catch{
        throw 'Windows no permite escribir en esa carpeta. Ejecuta Actualizar_Vectorizador_STL.bat como administrador, tras verificar la ruta.'
    }finally{
        if(Test-Path -LiteralPath $prueba){Remove-Item -LiteralPath $prueba -Force}
    }

    New-Item -ItemType Directory -Path $trabajo -Force | Out-Null
    Write-Host 'Descargando el ejecutable de prueba desde el Release de GitHub...'
    Invoke-WebRequest -Uri $download -OutFile $temporalZip -UseBasicParsing
    if((Get-Item $temporalZip).Length -lt 1000000){throw 'ZIP de programa inesperadamente pequeno.'}
    # Verificar el resumen SHA-256 comunicado por GitHub, si el servicio lo publica.
    $release=Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/tags/$tag" -Headers @{'User-Agent'='Vectorizador-Updater'}
    $registro=@($release.assets | Where-Object {$_.name -eq $asset})
    if($registro.Count -ne 1){throw 'El paquete no coincide con el Release previsto.'}
    if($registro[0].digest -and $registro[0].digest -match '^sha256:([0-9a-fA-F]{64})$'){
        $sha=(Get-FileHash $temporalZip -Algorithm SHA256).Hash
        if($sha -ine $Matches[1]){throw 'La comprobacion SHA-256 del programa ha fallado.'}
    }
    New-Item -ItemType Directory -Path $extraidos -Force | Out-Null
    Expand-Archive -LiteralPath $temporalZip -DestinationPath $extraidos -Force
    if(!(Test-Path -LiteralPath (Join-Path $extraidos 'Vectorizador.exe')) -or
       !(Test-Path -LiteralPath (Join-Path $extraidos '_internal') -PathType Container)){
        throw 'ZIP no valido: no contiene el ejecutable y sus librerias.'
    }
    $archivos=@(Get-ChildItem -LiteralPath $extraidos -Recurse -File)
    if($archivos.Count -lt 20){throw 'Paquete incompleto: no se han encontrado las librerias necesarias.'}
    $nombreCopia='Antes_STL_'+(Get-Date -Format 'yyyyMMdd_HHmmss')
    $carpetaCopia=Join-Path $copias $nombreCopia
    New-Item -ItemType Directory -Path $carpetaCopia -Force | Out-Null
    $manifiesto=New-Object System.Collections.ArrayList
    Write-Host ('Guardando copia recuperable: '+$carpetaCopia)
    # Guardar respaldo exacto de los archivos que se van a sobrescribir.
    foreach($archivo in $archivos){
        $rel=$archivo.FullName.Substring($extraidos.Length).TrimStart([char[]]@('\','/'))
        $objetivo=Join-Path $RutaInstalacion $rel
        if(Test-Path -LiteralPath $objetivo -PathType Leaf){
            $destinoCopia=Join-Path $carpetaCopia $rel
            New-Item -ItemType Directory -Path (Split-Path -Parent $destinoCopia) -Force | Out-Null
            Copy-Item -LiteralPath $objetivo -Destination $destinoCopia -Force
            [void]$respaldados.Add(@($rel,$destinoCopia,$objetivo))
        }
        [void]$manifiesto.Add($rel)
    }
    $metadatos=@{origen='Vectorizador V2.6 instalada';ubicacion=$RutaInstalacion;
      fecha=(Get-Date -Format 's');archivos_actualizados=@($manifiesto)}
    ($metadatos|ConvertTo-Json -Depth 5)|Set-Content -Path (Join-Path $carpetaCopia 'info_actualizacion.json') -Encoding UTF8
    Write-Host 'Sustituyendo SOLO los archivos del programa...'
    $instalado=$true
    foreach($archivo in $archivos){
        $rel=$archivo.FullName.Substring($extraidos.Length).TrimStart([char[]]@('\','/'))
        $objetivo=Join-Path $RutaInstalacion $rel
        $directorio=Split-Path -Parent $objetivo
        if(!(Test-Path -LiteralPath $directorio)){New-Item -ItemType Directory -Path $directorio -Force | Out-Null}
        Copy-Item -LiteralPath $archivo.FullName -Destination $objetivo -Force
    }
    $completado=$true
    Write-Host ''
    Write-Host 'ACTUALIZACION STL DE PRUEBA COMPLETADA.' -ForegroundColor Green
    Write-Host ('Instalacion: '+$RutaInstalacion)
    Write-Host ('Copia de recuperacion: '+$carpetaCopia)
    Write-Host 'Inicia Vectorizador desde su acceso directo habitual.'
    Write-Host 'En Extruir STL puedes activar la casilla de reparacion de prueba.'
    Write-Host 'La version oficial V2.6 y los trabajos privados NO se han borrado.'
}
catch {
    Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
    if($instalado -and !$completado){
        Write-Host 'Intentando recuperar los archivos originales desde la copia...'
        $errores=0
        foreach($item in $respaldados){
            try{Copy-Item -LiteralPath $item[1] -Destination $item[2] -Force}
            catch{$errores++}
        }
        if($errores){Write-Host "ATENCION: hubo $errores errores restaurando archivos; usa la copia conservada."}
        else{Write-Host 'Archivos originales respaldados restaurados; archivos nuevos residuales no se eliminan.'}
    }
    exit 1
}
finally{
    if(Test-Path -LiteralPath $trabajo){
        Remove-Item -LiteralPath $trabajo -Recurse -Force -ErrorAction SilentlyContinue
    }
}
