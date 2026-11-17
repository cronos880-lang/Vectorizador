# Restaurar los binarios de Vectorizador anteriores a la actualización STL.
# No elimina archivos de proyectos ni toca la carpeta Archivos.
$ErrorActionPreference='Stop'
try{
    $carpeta=Join-Path $env:LOCALAPPDATA 'Vectorizador\Copias_actualizacion_STL'
    $copias=@(Get-ChildItem -LiteralPath $carpeta -Directory -ErrorAction Stop | Sort-Object Name -Descending)
    if(!$copias.Count){throw 'No se han encontrado copias de seguridad de esta actualizacion.'}
    Write-Host "Copias disponibles:"
    for($i=0;$i -lt $copias.Count;$i++){
        Write-Host ("[$($i+1)] "+$copias[$i].Name)
    }
    $numero=Read-Host "Indica el numero de copia que quieres restaurar (0 para cancelar)"
    if($numero -notmatch '^\d+$' -or [int]$numero -eq 0){exit 0}
    $indice=[int]$numero-1
    if($indice -lt 0 -or $indice -ge $copias.Count){throw 'Numero incorrecto.'}
    $base=$copias[$indice].FullName
    $info=Get-Content -LiteralPath (Join-Path $base 'info_actualizacion.json') -Raw | ConvertFrom-Json
    $destino=$info.ubicacion
    if(!(Test-Path -LiteralPath (Join-Path $destino 'Vectorizador.exe'))){
        throw 'No se ha localizado el Vectorizador instalado.'
    }
    if(Get-Process -Name Vectorizador -ErrorAction SilentlyContinue){
        throw 'Cierra Vectorizador desde la bandeja antes de restaurar.'
    }
    $decidir=Read-Host ("Restaurar los archivos de "+$base+" sobre "+$destino+"? (S/N)")
    if($decidir -notmatch '^[sS]$'){exit 0}
    $archivos=@(Get-ChildItem -LiteralPath $base -Recurse -File | Where-Object {$_.Name -ne 'info_actualizacion.json'})
    foreach($fichero in $archivos){
        $relativo=$fichero.FullName.Substring($base.Length).TrimStart([char[]]@('\','/'))
        $ruta=Join-Path $destino $relativo
        $padre=Split-Path -Parent $ruta
        if(!(Test-Path -LiteralPath $padre)){New-Item -ItemType Directory -Path $padre -Force | Out-Null}
        Copy-Item -LiteralPath $fichero.FullName -Destination $ruta -Force
    }
    Write-Host 'Archivos de la version anterior restaurados.' -ForegroundColor Green
    Write-Host 'Se han conservado las carpetas de datos y los archivos nuevos que no estaban en la copia.'
}catch{
    Write-Host ("No se pudo completar la restauracion: "+$_.Exception.Message) -ForegroundColor Red
    exit 1
}
