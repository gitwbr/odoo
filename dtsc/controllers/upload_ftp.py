from odoo import http
from odoo.http import request, Response
from ..models.upload_ftp import UploadModel
import json
import os
import datetime

class UploadController(http.Controller):
    
    @http.route('/dtsc/upload_file_chunk', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_file_chunk(self):
        print('Upload file chunk method called')

        file_chunk = request.httprequest.files.get('fileChunk')
        if file_chunk:
            chunk_index = int(request.params.get('chunkIndex'))
            total_chunks = int(request.params.get('totalChunks'))
            user_filename = request.params.get('filename', '')
            file_extension = request.params.get('file_extension', '')
            folder = request.params.get('folder', '其它')
            if user_filename == "false":
                user_filename = ""
            if folder == "false":
                folder = "其它"

            temp_folder = "/tmp/odoo/"  # 临时文件夹路径
            if not os.path.exists(temp_folder):
                os.makedirs(temp_folder)

            # 获取或创建唯一的文件名
            filename_storage_file = os.path.join(temp_folder, user_filename + "_filename")
            if chunk_index == 0:
                # 对于第一个分片，创建并存储唯一的文件名
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_filename = f"{user_filename}-{current_time}.{file_extension}"
                with open(filename_storage_file, "w") as f:
                    f.write(new_filename)
            else:
                # 读取存储的文件名
                with open(filename_storage_file, "r") as f:
                    new_filename = f.read()

            temp_filename = os.path.join(temp_folder, new_filename + ".part" + str(chunk_index))
            final_filename = os.path.join(temp_folder, new_filename)

            with open(temp_filename, "ab") as temp_file:
                temp_file.write(file_chunk.read())

            if chunk_index == total_chunks - 1:
                # 重组所有分片为最终文件
                with open(final_filename, "wb") as final_file:
                    for i in range(total_chunks):
                        part_filename = os.path.join(temp_folder, new_filename + ".part" + str(i))
                        with open(part_filename, "rb") as part_file:
                            final_file.write(part_file.read())
                        os.remove(part_filename)

                # 上传文件到FTP服务器
                uploader = UploadModel()
                with open(final_filename, 'rb') as file_content:
                    success = uploader.upload_to_ftp(file_content, new_filename, folder)
                os.remove(final_filename)

                if success:
                    return Response(json.dumps({'success': True, 'message': 'File uploaded successfully', 'filename': new_filename}), content_type='application/json;charset=utf-8', status=200)
                else:
                    return Response(json.dumps({'success': False, 'message': 'File upload to FTP failed'}), content_type='application/json;charset=utf-8', status=500)
            else:
                return Response(json.dumps({'success': True, 'message': 'Chunk uploaded successfully'}), content_type='application/json;charset=utf-8', status=200)
        else:
            return Response(json.dumps({'success': False, 'message': 'No file chunk provided'}), content_type='application/json;charset=utf-8', status=400)


    @http.route('/dtsc/upload_file', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_file(self):
        print('Upload file method called')
        
        file_content = request.httprequest.files.get('custom_file')
        if file_content:
            # 安全获取上传文件的实际文件名
            original_filename = file_content.filename

            # 提取上传文件的扩展名
            _, file_extension = os.path.splitext(original_filename)

            # 获取用户指定的文件名和文件夹
            user_filename = request.params.get('filename', '')
            folder = request.params.get('folder', '其它')
            if user_filename == "false":
                user_filename = ""
            if folder == "false":
                folder = "其它"

            # 获取当前时间
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 生成新的文件名（包含用户指定的名称、当前时间戳和文件的实际后缀）
            new_filename = f"{user_filename}-{current_time}{file_extension}"

            # 读取文件内容
            file_content = file_content.read()
            print("File content preview:", file_content[:10])

            print(f'Received file: {new_filename} in folder: {folder}')

            #uploader = UploadModel()
            uploader = request.env['upload.model']
            success = uploader.upload_to_ftp(file_content, new_filename, folder)

            if success:
                print('File uploaded successfully')
                return Response(json.dumps({'success': True, 'message': 'File uploaded successfully', 'filename': new_filename}), content_type='application/json;charset=utf-8', status=200)
            else:
                print('File upload failed')
                return Response(json.dumps({'success': False, 'message': 'File upload failed'}), content_type='application/json;charset=utf-8', status=500)
        else:
            return Response(json.dumps({'success': False, 'message': 'No file provided'}), content_type='application/json;charset=utf-8', status=400)

    @http.route('/dtsc/payment_upload_file', type='http', auth='user', methods=['POST'], csrf=False)
    def test_endpoint(self, **kwargs):
        
        print('Upload file method called')
        
        file_content = request.httprequest.files.get('custom_file')
        user_filename = request.params.get('filename', '')
        print(f'user_filename: {user_filename}')
        if file_content:
            # 安全获取上传文件的实际文件名
            original_filename = file_content.filename

            # 提取上传文件的扩展名
            _, file_extension = os.path.splitext(original_filename)

            # 获取用户指定的文件名和文件夹
            user_filename = request.params.get('filename', '')
            #folder = request.params.get('folder', '其它')
            current_user = request.env.user
            folder = current_user.name if current_user else '其它'
        
            if user_filename == "false":
                user_filename = ""
            if folder == "false":
                folder = "其它"

            # 获取当前时间
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 生成新的文件名（包含用户指定的名称、当前时间戳和文件的实际后缀）
            new_filename = f"{user_filename}-{current_time}{file_extension}"

            # 读取文件内容
            file_content = file_content.read()
            print("File content preview:", file_content[:10])

            print(f'Received file: {new_filename} in folder: {folder}')

            #uploader = UploadModel()
            uploader = request.env['upload.model']
            success = uploader.upload_to_ftp(file_content, new_filename, folder)
            if success:
                print('File uploaded successfully')
                return Response(json.dumps({'success': True, 'message': 'File uploaded successfully', 'filename': new_filename}), content_type='application/json;charset=utf-8', status=200)
            else:
                print('File upload failed——27')
                return Response(json.dumps({'success': False, 'message': 'File upload failed'}), content_type='application/json;charset=utf-8', status=200)
        else:
            return Response(json.dumps({'success': False, 'message': 'No file provided'}), content_type='application/json;charset=utf-8', status=400)