import hashlib
import base64
import boto3
import ffmpeg
import os
import sys
from pathlib import Path
import random
import time

# Configuración de Wasabi
def setup_wasabi_client():
    return boto3.client(
        's3',
        region_name='eu-west-2',
        endpoint_url='https://s3.eu-west-2.wasabisys.com',
        aws_access_key_id='YWXIDYPDHU8UJFSLB0C9',
        aws_secret_access_key='9tlwrIzRIL4Z2PzOBgAmPZwGCjI5pOdajer8LePt'
    )

# Hashing
def hash_name(name, invert=True):
    secret = 'SECRET_KEY'
    input_str = f"{secret}{name}" if not invert else f"{name} {secret}"
    binary_hash = hashlib.md5(input_str.encode()).digest()
    base64_value = base64.b64encode(binary_hash).decode('utf-8')
    return base64_value.replace('=', '').replace('+', '-').replace('/', '_')

# Creación de directorios
def make_dir(path):
    os.makedirs(path, exist_ok=True)

# Funciones para generar URL con CDN aleatorio y token seguro
CDNS = ['192.168.56.2', '192.168.56.3']

def get_random_cdn():
    return random.choice(CDNS)

def generate_secure_path_hash(expires, client_ip):
    return hash_name(f"{expires} {client_ip}", True)

def upload_large_files(s3_client, file_path, bucket_name):
    # Construye la clave del objeto incluyendo el directorio 'vod' y el subdirectorio con el hash
    file_key = str(file_path).replace('\\', '/')  # Asegura usar barras normales para S3
    try:
        s3_client.upload_file(str(file_path), bucket_name, file_key)
        print(f"{file_path} uploaded successfully to {bucket_name}/{file_key}")
    except Exception as e:
        print(f"An error occurred while uploading {file_path} to {bucket_name}/{file_key}: {str(e)}")

def get_url(video_id, client_ip, qualities):
    expires = str(int(time.time() + 3600))  # 1 hour expires
    token = generate_secure_path_hash(expires, client_ip)
    quality_str = ','.join([q[:-1] for q in qualities.split(',')])
    url = f"http://{get_random_cdn()}/hls/vod/{video_id}/{token}/{expires}/_,{quality_str},0p.mp4.play/master.m3u8"
    return url

def transcode(filePath):
    s3_client = setup_wasabi_client()
    make_dir('vod')
    fileName = Path(filePath).stem
    videoName = hash_name(fileName)
    # Crear la ruta completa del directorio local que incluye 'vod'
    mp4Dir = Path('vod') / videoName
    make_dir(mp4Dir)

    probe = ffmpeg.probe(filePath)
    video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
    height = int(video_stream['height'])

    qualities = [
        {'w': 842, 'h': 480, 'vbr': 1400, 'abr': 128},
        {'w': 1280, 'h': 720, 'vbr': 2800, 'abr': 160},
        {'w': 1920, 'h': 1080, 'vbr': 5000, 'abr': 192},
    ]

    if height < 480:
        max_quality = 0
    elif height < 720:
        max_quality = 1
    else:
        max_quality = 2

    for q in qualities[:max_quality + 1]:
        output_file = mp4Dir / f"_{q['h']}p.mp4"
        ffmpeg.input(filePath).output(
            str(output_file), vf=f"scale={q['w']}:{q['h']}", vcodec='libx264', acodec='aac', ac=2,
            **{'b:v': f"{q['vbr']}k", 'maxrate': f"{q['vbr']}k", 'bufsize': f"{q['vbr']}k", 'b:a': f"{q['abr']}k"}
        ).run(overwrite_output=True)
        print(f"Processed {output_file}")
        upload_large_files(s3_client, output_file, 'servidorhls')

if __name__ == "__main__":
    # Use la función transcode con un archivo específico
    #transcode('Metallica.mp4')
    
    # Ejemplo para obtener URL
    if len(sys.argv) > 2:
        video_id = hash_name(sys.argv[1], True)
        client_ip = sys.argv[2]
        qualities = sys.argv[3]
        print(get_url(video_id, client_ip, qualities))
