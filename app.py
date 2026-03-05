import random
import string
from datetime import datetime, timedelta
import io
import json
import os
import zipfile
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, request, Response
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity, get_jwt
)
from flask_cors import CORS


class Config:
    """应用配置类"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'your-strong-random-secret-key-987654')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'your-jwt-secret-key-123456')
    Projects_DIR = Path("./projects")
    Testsuite_DIR = Path("./testsuites")
    Testcase_DIR = Path("./testcases")
    Testrun_DIR = Path("./testrun")

class UserManager:
    """用户管理类"""
    USERS = {
        "admin": {
            "email": "test@admin.com",
            "password": "test123456",
            "role": "admin",
            "permissions": ["read", "write", "delete", "manage_users"]
        },
        "user1": {
            "email": "caigou@mumi.com",
            "password": "mumi123456",
            "role": "admin",
            "permissions": ["read", "write", "delete", "manage_users"]
        },
        "user2": {
            "email": "caiwu@mumi.com",
            "password": "mumi123456",
            "role": "admin",
            "permissions": ["read", "write", "delete", "manage_users"]
        },
        "user3": {
            "email": "kefu@mumi.com",
            "password": "mumi123456",
            "role": "user",
            "permissions": ["read"]
        }
    }

    @classmethod
    def authenticate_user(cls, email, password):
        """验证用户凭据"""
        for username, user_info in cls.USERS.items():
            if user_info["email"] == email and user_info["password"] == password:
                return {
                    "username": username,
                    "email": user_info["email"],
                    "role": user_info["role"],
                    "permissions": user_info["permissions"]
                }
        return None

    @classmethod
    def get_user_by_email(cls, email):
        """通过邮箱查找用户"""
        for username, user_info in cls.USERS.items():
            if user_info["email"] == email:
                return {
                    "username": username,
                    "email": user_info["email"],
                    "role": user_info["role"],
                    "permissions": user_info["permissions"]
                }
        return None

    @classmethod
    def add_user(cls, username, email, password, role="user"):
        """添加新用户"""
        if username in cls.USERS:
            return False, "用户名已存在"

        if any(user_info["email"] == email for user_info in cls.USERS.values()):
            return False, "邮箱已被使用"

        permissions = ["read", "write", "delete", "manage_users"] if role == "admin" else ["read",
                                                                                           "write"] if role == "user" else [
            "read"]

        cls.USERS[username] = {
            "email": email,
            "password": password,
            "role": role,
            "permissions": permissions
        }
        return True, "用户添加成功"

    @classmethod
    def delete_user(cls, username):
        """删除用户"""
        if username not in cls.USERS:
            return False, "用户不存在"

        if cls.USERS[username]["role"] == "admin" and sum(1 for u in cls.USERS.values() if u["role"] == "admin") <= 1:
            return False, "不能删除最后一个管理员"

        del cls.USERS[username]
        return True, "用户删除成功"

    @classmethod
    def update_user_role(cls, username, new_role):
        """更新用户角色"""
        if username not in cls.USERS:
            return False, "用户不存在"

        if cls.USERS[username]["role"] == "admin" and new_role != "admin" and sum(
                1 for u in cls.USERS.values() if u["role"] == "admin") <= 1:
            return False, "不能移除最后一个管理员的角色"

        cls.USERS[username]["role"] = new_role
        permissions = ["read", "write", "delete", "manage_users"] if new_role == "admin" else ["read",
                                                                                               "write"] if new_role == "user" else [
            "read"]
        cls.USERS[username]["permissions"] = permissions
        return True, "用户角色更新成功"


class FileManager:
    """文件管理类"""

    @staticmethod
    def ensure_directories_exist():
        """确保所有必需目录存在"""
        for directory in [Config.Projects_DIR, Config.Testsuite_DIR, Config.Testcase_DIR, Config.Testrun_DIR]:
            directory.mkdir(exist_ok=True)

    @staticmethod
    def get_directory_by_type(file_type):
        """根据类型获取对应目录"""
        if file_type == 'projects':
            return Config.Projects_DIR
        elif file_type == 'testsuites':
            return Config.Testsuite_DIR
        elif file_type == 'testcases':
            return Config.Testcase_DIR
        elif file_type == 'testrun':
            return Config.Testrun_DIR
        else:
            raise ValueError(f"Invalid file type: {file_type}")


class DataProcessor:
    """数据处理器"""

    @staticmethod
    def generate_unique_key(item):
        """生成唯一键用于去重"""
        sorted_items = sorted(item.items(), key=lambda x: x[0])
        key_parts = []
        for key, value in sorted_items:
            if isinstance(value, (int, float)):
                val_str = f"{value:.6f}"
            elif value is None:
                val_str = ""
            else:
                val_str = str(value).strip()
            key_parts.append(f"{key}:{val_str}")
        return "|".join(key_parts)


    @staticmethod
    def write_to_json(new_data, original_filename, json_type):
        """将解析后的Excel数据写入JSON文件"""
        if not isinstance(new_data, list) or len(new_data) == 0:
            print("ℹ️ 提示：新数据为空或非列表类型，无需写入")
            return 0

        # 生成去重后的新数据字典
        new_key_dict = {DataProcessor.generate_unique_key(item): item for item in new_data}
        added_count = len(new_key_dict)

        # 获取文件名
        core_filename = original_filename
        while '.' in core_filename:
            last_dot_pos = core_filename.rfind('.')
            if last_dot_pos == 0:
                break
            core_filename = core_filename[:last_dot_pos]
        json_filename = f"{core_filename}.json"

        # 获取目录
        json_file_path = FileManager.get_directory_by_type(json_type) / json_filename

        try:
            # 写入JSON文件
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(list(new_key_dict.values()), f, ensure_ascii=False, indent=4, default=DataProcessor.json_serializable)

            print(f"✅ JSON文件已保存：{json_file_path.absolute()}")
            return added_count

        except Exception as e:
            print(f"❌ 创建JSON文件失败：{str(e)}")
            return 0

    @staticmethod
    def read_json_file(json_filename, file_type):
        """读取JSON文件"""
        try:
            json_file_path = FileManager.get_directory_by_type(file_type) / json_filename
            with open(json_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"文件 {json_file_path} 不存在")
            return []
        except Exception as e:
            print(f"读取失败：{e}")
            return []

    @staticmethod
    def read_all_json_files(file_type):
        """读取指定类型目录下的所有JSON文件并合并内容"""
        try:
            directory = FileManager.get_directory_by_type(file_type)

            if not directory.exists():
                print(f"目录 {directory} 不存在")
                return []

            all_data = []

            # 遍历目录中的所有JSON文件
            for json_file_path in directory.glob("*.json"):
                try:
                    with open(json_file_path, "r", encoding="utf-8") as f:
                        file_data = json.load(f)

                        # 如果文件内容是列表，则扩展到总数据中
                        if isinstance(file_data, list):
                            all_data.extend(file_data)
                        # 如果文件内容是单个对象，则添加到总数据中
                        elif isinstance(file_data, dict):
                            all_data.append(file_data)
                        else:
                            print(f"警告：文件 {json_file_path} 包含非列表/非字典数据，跳过")

                except json.JSONDecodeError as e:
                    print(f"JSON解析错误，跳过文件 {json_file_path}: {e}")
                except Exception as e:
                    print(f"读取文件 {json_file_path} 时发生错误: {e}")

            print(f"成功读取 {len(all_data)} 条记录")
            return all_data

        except Exception as e:
            print(f"读取目录 {directory} 时发生错误：{e}")
            return []

    @staticmethod
    def process_save_projects(data):
        try:
            json_file_path = FileManager.get_directory_by_type('projects') / 'projects.json'

            # 1️⃣ 尝试读取已有数据（若文件存在且可解析）
            existing_data = []
            if json_file_path.exists():
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            print(f"⚠️  警告：{json_file_path} 格式异常，重置为 []")
                            existing_data = []
                except (json.JSONDecodeError, OSError) as e:
                    print(f"⚠️  读取旧数据失败（将清空重建）：{e}")
                    existing_data = []

            existing_data.append(data)

            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

            print(f"✅ JSON文件已保存")
            return jsonify({
                "code": 200,
                "msg": "保存成功",
            }), 200

        except Exception as e:
            print(f"❌ 保存 voucher 失败：{str(e)}")
            return ResponseHandler.error(f"保存失败：{str(e)}", 500)

    @staticmethod
    def process_update_project(data):
        try:
            json_file_path = FileManager.get_directory_by_type('projects') / 'projects.json'

            existing_data = []
            if json_file_path.exists():
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            existing_data = []
                except (json.JSONDecodeError, OSError) as e:
                    existing_data = []

            updated = False
            for i, existing_item in enumerate(existing_data):
                if existing_item.get('id') == data['id']:
                    # 找到匹配的项目，进行更新
                    existing_data[i].update(data)
                    updated = True
                    print(f"✅ 项目 ID {data['id']} 已更新: {existing_data[i]}")
                    break


            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

            print(f"✅ JSON文件已保存")
            return jsonify({
                "code": 200,
                "msg": "保存成功",
            }), 200

        except Exception as e:
            print(f"❌ 保存 voucher 失败：{str(e)}")
            return ResponseHandler.error(f"保存失败：{str(e)}", 500)


    @staticmethod
    def process_delete_project(project_id):
        try:
            json_file_path = FileManager.get_directory_by_type('projects') / 'projects.json'

            existing_data = []
            if json_file_path.exists():
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            existing_data = []
                except (json.JSONDecodeError, OSError) as e:
                    existing_data = []

            for i, p in enumerate(existing_data):
                if p["id"] == project_id:
                    del existing_data[i]
                    print(f"✅ Deleted project at index {i}")
                    break
            else:
                print(f"⚠️  Project with id '{project_id}' not found.")

            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

            print(f"✅ JSON文件已保存")
            return jsonify({
                "code": 200,
                "msg": "删除成功",
            }), 200

        except Exception as e:
            print(f"❌ 保存 voucher 失败：{str(e)}")
            return ResponseHandler.error(f"保存失败：{str(e)}", 500)

    @staticmethod
    def process_save_testsuite(data):
        try:
            json_file_path = FileManager.get_directory_by_type('testsuites') / 'testsuites.json'

            # 1️⃣ 尝试读取已有数据（若文件存在且可解析）
            existing_data = []
            if json_file_path.exists():
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            print(f"⚠️  警告：{json_file_path} 格式异常，重置为 []")
                            existing_data = []
                except (json.JSONDecodeError, OSError) as e:
                    print(f"⚠️  读取旧数据失败（将清空重建）：{e}")
                    existing_data = []

            existing_data.append(data)

            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

            print(f"✅ JSON文件已保存")
            return jsonify({
                "code": 200,
                "msg": "保存成功",
            }), 200

        except Exception as e:
            print(f"❌ 保存 voucher 失败：{str(e)}")
            return ResponseHandler.error(f"保存失败：{str(e)}", 500)


    @staticmethod
    def process_update_testsuite(data):
        try:
            json_file_path = FileManager.get_directory_by_type('testsuites') / 'testsuites.json'

            existing_data = []
            if json_file_path.exists():
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            existing_data = []
                except (json.JSONDecodeError, OSError) as e:
                    existing_data = []

            updated = False
            for i, existing_item in enumerate(existing_data):
                if existing_item.get('id') == data['id']:
                    # 找到匹配的项目，进行更新
                    existing_data[i].update(data)
                    updated = True
                    print(f"✅ 项目 ID {data['id']} 已更新: {existing_data[i]}")
                    break


            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

            print(f"✅ JSON文件已保存")
            return jsonify({
                "code": 200,
                "msg": "保存成功",
            }), 200

        except Exception as e:
            print(f"❌ 保存 voucher 失败：{str(e)}")
            return ResponseHandler.error(f"保存失败：{str(e)}", 500)


    @staticmethod
    def process_delete_testsuite(testsuite_id):
        try:
            json_file_path = FileManager.get_directory_by_type('testsuites') / 'testsuites.json'

            existing_data = []
            if json_file_path.exists():
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            existing_data = []
                except (json.JSONDecodeError, OSError) as e:
                    existing_data = []

            for i, p in enumerate(existing_data):
                if p["id"] == testsuite_id:
                    del existing_data[i]
                    print(f"✅ Deleted project at index {i}")
                    break
            else:
                print(f"⚠️  Project with id '{testsuite_id}' not found.")

            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

            print(f"✅ JSON文件已保存")
            return jsonify({
                "code": 200,
                "msg": "删除成功",
            }), 200

        except Exception as e:
            print(f"❌ 保存 voucher 失败：{str(e)}")
            return ResponseHandler.error(f"保存失败：{str(e)}", 500)


    @staticmethod
    def process_save_testcase(data):
        try:
            json_file_path = FileManager.get_directory_by_type('testcases') / 'testcases.json'

            # 1️⃣ 尝试读取已有数据（若文件存在且可解析）
            existing_data = []
            if json_file_path.exists():
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            print(f"⚠️  警告：{json_file_path} 格式异常，重置为 []")
                            existing_data = []
                except (json.JSONDecodeError, OSError) as e:
                    print(f"⚠️  读取旧数据失败（将清空重建）：{e}")
                    existing_data = []

            existing_data.append(data)

            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

            print(f"✅ JSON文件已保存")
            return jsonify({
                "code": 200,
                "msg": "保存成功",
            }), 200

        except Exception as e:
            print(f"❌ 保存 voucher 失败：{str(e)}")
            return ResponseHandler.error(f"保存失败：{str(e)}", 500)


    @staticmethod
    def process_update_testcase(data):
        try:
            json_file_path = FileManager.get_directory_by_type('testcases') / 'testcases.json'

            existing_data = []
            if json_file_path.exists():
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            existing_data = []
                except (json.JSONDecodeError, OSError) as e:
                    existing_data = []

            updated = False
            for i, existing_item in enumerate(existing_data):
                if existing_item.get('id') == data['id']:
                    # 找到匹配的项目，进行更新
                    existing_data[i].update(data)
                    updated = True
                    print(f"✅ 项目 ID {data['id']} 已更新: {existing_data[i]}")
                    break


            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

            print(f"✅ JSON文件已保存")
            return jsonify({
                "code": 200,
                "msg": "保存成功",
            }), 200

        except Exception as e:
            print(f"❌ 保存 voucher 失败：{str(e)}")
            return ResponseHandler.error(f"保存失败：{str(e)}", 500)


    @staticmethod
    def process_delete_testcase(testcase_id):
        try:
            json_file_path = FileManager.get_directory_by_type('testcases') / 'testcases.json'

            existing_data = []
            if json_file_path.exists():
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            existing_data = []
                except (json.JSONDecodeError, OSError) as e:
                    existing_data = []

            for i, p in enumerate(existing_data):
                if p["id"] == testcase_id:
                    del existing_data[i]
                    print(f"✅ Deleted project at index {i}")
                    break
            else:
                print(f"⚠️  Project with id '{testcase_id}' not found.")

            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

            print(f"✅ JSON文件已保存")
            return jsonify({
                "code": 200,
                "msg": "删除成功",
            }), 200

        except Exception as e:
            print(f"❌ 保存 voucher 失败：{str(e)}")
            return ResponseHandler.error(f"保存失败：{str(e)}", 500)

class ResponseHandler:
    """响应处理器"""

    @staticmethod
    def success(data=None, msg="操作成功"):
        return jsonify({"code": 200, "msg": msg, "data": data})

    @staticmethod
    def error(msg="操作失败", code=500, data=None):
        return jsonify({"code": code, "msg": msg, "data": data}), code


def require_permission(permission_needed):
    """装饰器：检查用户权限"""

    def decorator(fn):
        def wrapper(*args, **kwargs):
            current_user = get_jwt_identity()
            user_info = UserManager.get_user_by_email(current_user)

            if not user_info:
                return ResponseHandler.error("用户信息无效", 401)

            if permission_needed not in user_info["permissions"]:
                return ResponseHandler.error(f"权限不足，需要 {permission_needed} 权限", 403)

            return fn(*args, **kwargs)

        wrapper.__name__ = fn.__name__
        return wrapper

    return decorator


app = Flask(__name__)
CORS(app)
app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["JWT_SECRET_KEY"] = Config.JWT_SECRET_KEY
jwt = JWTManager(app)

FileManager.ensure_directories_exist()


@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        if not data or "email" not in data or "password" not in data:
            return ResponseHandler.error("请传入邮箱和密码", 400)

        input_email = data["email"].strip()
        input_password = data["password"].strip()

        user_info = UserManager.authenticate_user(input_email, input_password)
        if not user_info:
            return ResponseHandler.error("邮箱或密码错误", 401)

        # 生成Token
        expires_delta = timedelta(hours=8)
        access_token = create_access_token(
            identity=user_info["email"],
            additional_claims={
                "username": user_info["username"],
                "role": user_info["role"],
                "permissions": user_info["permissions"]
            },
            expires_delta=expires_delta
        )

        return jsonify({
            "code": 200,
            "msg": "登录成功",
            "data": {
                "access_token": access_token,
                "expires_in": 8 * 3600,
                "user_info": {
                    "username": user_info["username"],
                    "email": user_info["email"],
                    "role": user_info["role"],
                    "permissions": user_info["permissions"]
                }
            }
        }), 200

    except Exception as e:
        return ResponseHandler.error(f"服务器错误：{str(e)}", 500)


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return ResponseHandler.error("Token已过期，请重新登录", 401)


@jwt.invalid_token_loader
def invalid_token_callback(error):
    return ResponseHandler.error("Token无效，请重新登录", 401)


@app.route("/api/users", methods=["GET"])
@jwt_required()
@require_permission("manage_users")
def get_users():
    """获取所有用户信息（仅管理员）"""
    try:
        users_list = []
        for username, user_info in UserManager.USERS.items():
            users_list.append({
                "username": username,
                "email": user_info["email"],
                "role": user_info["role"],
                "permissions": user_info["permissions"]
            })

        return ResponseHandler.success({
            "users": users_list,
            "total": len(users_list)
        }, "获取用户列表成功")
    except Exception as e:
        return ResponseHandler.error(f"获取用户列表失败：{str(e)}", 500)


@app.route("/api/users", methods=["POST"])
@jwt_required()
@require_permission("manage_users")
def add_user():
    """添加新用户（仅管理员）"""
    try:
        data = request.get_json()
        if not data or "username" not in data or "email" not in data or "password" not in data:
            return ResponseHandler.error("请提供用户名、邮箱和密码", 400)

        username = data["username"].strip()
        email = data["email"].strip()
        password = data["password"].strip()
        role = data.get("role", "user").strip()

        if role not in ["admin", "user", "viewer"]:
            return ResponseHandler.error("角色必须是 admin、user 或 viewer", 400)

        success, message = UserManager.add_user(username, email, password, role)
        if success:
            return ResponseHandler.success(None, message)
        else:
            return ResponseHandler.error(message, 400)
    except Exception as e:
        return ResponseHandler.error(f"添加用户失败：{str(e)}", 500)


@app.route("/api/users/<username>", methods=["DELETE"])
@jwt_required()
@require_permission("manage_users")
def delete_user(username):
    """删除用户（仅管理员）"""
    try:
        success, message = UserManager.delete_user(username)
        if success:
            return ResponseHandler.success(None, message)
        else:
            return ResponseHandler.error(message, 400)
    except Exception as e:
        return ResponseHandler.error(f"删除用户失败：{str(e)}", 500)


@app.route("/api/users/<username>/role", methods=["PUT"])
@jwt_required()
@require_permission("manage_users")
def update_user_role(username):
    """更新用户角色（仅管理员）"""
    try:
        data = request.get_json()
        if not data or "role" not in data:
            return ResponseHandler.error("请提供新的角色", 400)

        new_role = data["role"].strip()
        if new_role not in ["admin", "user", "viewer"]:
            return ResponseHandler.error("角色必须是 admin、user 或 viewer", 400)

        success, message = UserManager.update_user_role(username, new_role)
        if success:
            return ResponseHandler.success(None, message)
        else:
            return ResponseHandler.error(message, 400)
    except Exception as e:
        return ResponseHandler.error(f"更新用户角色失败：{str(e)}", 500)


@app.route('/api/invoices/files', methods=['GET'])
@jwt_required()
def get_invoices_files():
    receive_type = request.args.get('type', '').strip()
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:
        invoices_dir = FileManager.get_directory_by_type(receive_type)

        if not invoices_dir.exists():
            return ResponseHandler.error("文件夹不存在", 404, [])

        files = []
        for file_path in invoices_dir.iterdir():
            if file_path.is_file():
                file_size = file_path.stat().st_size
                files.append({
                    "file_name": file_path.name.replace(".json", ""),
                    "file_size": file_size,
                })

        return jsonify({
            "code": 200,
            "msg": "获取文件列表成功",
            "data": {
                "total": len(files),
                "files": files
            }
        }), 200

    except Exception as e:
        return ResponseHandler.error(f"获取文件列表失败：{str(e)}", 500, [])


@app.route('/api/projects', methods=['GET'])
@jwt_required()
def api_get_projects():
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:

        data = DataProcessor.read_all_json_files('projects').copy()
        # 将JSON数据压缩为ZIP二进制流
        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')

        response = Response(
            response=json_bytes,
            status=200,
        )
        return response

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)

@app.route('/api/create_projects', methods=['POST'])
@jwt_required()
def api_create_projects():
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:
        data = request.get_json()
        return DataProcessor.process_save_projects(data)

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)

@app.route('/api/update_project', methods=['PUT'])
@jwt_required()
def api_update_project():
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:
        data = request.get_json()
        return DataProcessor.process_update_project(data)

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)

@app.route('/api/delete_project/<project_id>', methods=['DELETE'])
@jwt_required()
def api_delete_project(project_id):
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:
        return DataProcessor.process_delete_project(project_id)

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)


@app.route('/api/testcases', methods=['GET'])
@jwt_required()
def api_get_testcase():
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:

        data = DataProcessor.read_all_json_files('testcases').copy()
        # 将JSON数据压缩为ZIP二进制流
        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')

        response = Response(
            response=json_bytes,
            status=200,
        )
        return response

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)

@app.route('/api/create_testcase', methods=['POST'])
@jwt_required()
def api_create_testcase():
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:
        data = request.get_json()
        return DataProcessor.process_save_testcase(data)

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)

@app.route('/api/update_testcase', methods=['PUT'])
@jwt_required()
def api_update_testcase():
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:
        data = request.get_json()
        return DataProcessor.process_update_testcase(data)

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)

@app.route('/api/delete_testcase/<testcase_id>', methods=['DELETE'])
@jwt_required()
def api_delete_testcase(testcase_id):
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:
        return DataProcessor.process_delete_testcase(testcase_id)

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)

@app.route('/api/testsuites', methods=['GET'])
@jwt_required()
def api_get_testsuites():
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:

        data = DataProcessor.read_all_json_files('testsuites').copy()
        # 将JSON数据压缩为ZIP二进制流
        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')

        response = Response(
            response=json_bytes,
            status=200,
        )
        return response

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)


@app.route('/api/create_testsuite', methods=['POST'])
@jwt_required()
def api_create_testsuite():
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:
        data = request.get_json()
        return DataProcessor.process_save_testsuite(data)

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)

@app.route('/api/update_testsuite', methods=['PUT'])
@jwt_required()
def api_update_testsuite():
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:
        data = request.get_json()
        return DataProcessor.process_update_testsuite(data)

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)

@app.route('/api/delete_testsuite/<testsuite_id>', methods=['DELETE'])
@jwt_required()
def api_delete_testsuite(testsuite_id):
    current_user = get_jwt_identity()
    jwt_data = get_jwt()

    # 验证token是否过期
    if jwt_data.get("exp") is None:
        return ResponseHandler.error("Token已过期，请重新登录", 401)

    try:
        return DataProcessor.process_delete_testsuite(testsuite_id)

    except Exception as e:
        return ResponseHandler.error(f"筛选失败：{str(e)}", 500)




if __name__ == '__main__':
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
    app.run(host="0.0.0.0", port=8000, debug=False)