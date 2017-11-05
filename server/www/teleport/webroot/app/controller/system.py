# -*- coding: utf-8 -*-

import datetime
import json
import shutil

import app.model.system as system_model
import tornado.gen
from app.base import mail
from app.base.configs import get_cfg
from app.base.controller import TPBaseHandler, TPBaseJsonHandler
from app.base.logger import *
from app.const import *
from app.model import syslog
from app.model import record
from app.base.core_server import core_service_async_post_http


class DoGetTimeHandler(TPBaseJsonHandler):
    def post(self):
        time_now = int(datetime.datetime.utcnow().timestamp())
        self.write_json(TPE_OK, data=time_now)


class ConfigHandler(TPBaseHandler):
    @tornado.gen.coroutine
    def get(self):
        ret = self.check_privilege(TP_PRIVILEGE_SYS_CONFIG)
        if ret != TPE_OK:
            return

        cfg = get_cfg()

        # core_detected = False
        req = {'method': 'get_config', 'param': []}
        _yr = core_service_async_post_http(req)
        code, ret_data = yield _yr
        if code != TPE_OK:
            cfg.update_core(None)
        else:
            cfg.update_core(ret_data)

        if not get_cfg().core.detected:
            total_size = 0
            free_size = 0
        else:
            total_size, _, free_size = shutil.disk_usage(get_cfg().core.replay_path)

        param = {
            'total_size': total_size,
            'free_size': free_size,
            'core_cfg': get_cfg().core,
            'sys_cfg': get_cfg().sys
        }

        self.render('system/config.mako', page_param=json.dumps(param))


class RoleHandler(TPBaseHandler):
    def get(self):
        ret = self.check_privilege(TP_PRIVILEGE_SYS_ROLE)
        if ret != TPE_OK:
            return
        self.render('system/role.mako')


class DoRoleUpdateHandler(TPBaseJsonHandler):
    @tornado.gen.coroutine
    def post(self):
        ret = self.check_privilege(TP_PRIVILEGE_SYS_ROLE)
        if ret != TPE_OK:
            return

        args = self.get_argument('args', None)
        if args is None:
            return self.write_json(TPE_PARAM)
        try:
            args = json.loads(args)
        except:
            return self.write_json(TPE_JSON_FORMAT)

        try:
            role_id = int(args['role_id'])
            role_name = args['role_name']
            privilege = int(args['privilege'])
        except:
            log.e('\n')
            return self.write_json(TPE_PARAM)

        if role_id == 0:
            err, role_id = system_model.add_role(self, role_name, privilege)
        else:
            if role_id == 1:
                return self.write_json(TPE_FAILED, '禁止修改系统管理员角色！')
            err = system_model.update_role(self, role_id, role_name, privilege)

        return self.write_json(err, data=role_id)


class DoRoleRemoveHandler(TPBaseJsonHandler):
    @tornado.gen.coroutine
    def post(self):
        ret = self.check_privilege(TP_PRIVILEGE_SYS_ROLE)
        if ret != TPE_OK:
            return

        args = self.get_argument('args', None)
        if args is None:
            return self.write_json(TPE_PARAM)
        try:
            args = json.loads(args)
        except:
            return self.write_json(TPE_JSON_FORMAT)

        try:
            role_id = int(args['role_id'])
        except:
            log.e('\n')
            return self.write_json(TPE_PARAM)

        if role_id == 1:
            return self.write_json(TPE_FAILED, '禁止删除系统管理员角色！')
        err = system_model.remove_role(self, role_id)

        return self.write_json(err)


class SysLogHandler(TPBaseHandler):
    def get(self):
        ret = self.check_privilege(TP_PRIVILEGE_SYS_LOG)
        if ret != TPE_OK:
            return
        self.render('system/syslog.mako')


class DoGetLogsHandler(TPBaseJsonHandler):
    def post(self):
        # return self.write_json(0, data=[])

        filter = dict()
        order = dict()
        order['name'] = 'log_time'
        order['asc'] = False
        limit = dict()
        limit['page_index'] = 0
        limit['per_page'] = 25

        args = self.get_argument('args', None)
        if args is not None:
            args = json.loads(args)

            tmp = list()
            _filter = args['filter']
            if _filter is not None:
                for i in _filter:
                    if i == 'user_name':
                        _x = _filter[i].strip()
                        if _x == '全部':
                            tmp.append(i)

                    if i == 'search':
                        _x = _filter[i].strip()
                        if len(_x) == 0:
                            tmp.append(i)
                        continue

                for i in tmp:
                    del _filter[i]

                filter.update(_filter)

        _limit = args['limit']
        if _limit['page_index'] < 0:
            _limit['page_index'] = 0
        if _limit['per_page'] < 10:
            _limit['per_page'] = 10
        if _limit['per_page'] > 100:
            _limit['per_page'] = 100

        limit.update(_limit)

        _order = args['order']
        if _order is not None:
            order['name'] = _order['k']
            order['asc'] = _order['v']

        err, total, record_list = syslog.get_logs(filter, order, _limit)
        if err != TPE_OK:
            return self.write_json(err)
        ret = dict()
        ret['page_index'] = limit['page_index']
        ret['total'] = total
        ret['data'] = record_list

        return self.write_json(0, data=ret)


class DoSaveCfgHandler(TPBaseJsonHandler):
    def post(self):
        ret = self.check_privilege(TP_PRIVILEGE_SYS_CONFIG)
        if ret != TPE_OK:
            return

        args = self.get_argument('args', None)
        if args is None:
            return self.write_json(TPE_PARAM)
        try:
            args = json.loads(args)
        except:
            return self.write_json(TPE_JSON_FORMAT)

        try:
            if 'smtp' in args:
                _cfg = args['smtp']
                _server = _cfg['server']
                _port = _cfg['port']
                _ssl = _cfg['ssl']
                _sender = _cfg['sender']
                _password = _cfg['password']

                err = system_model.save_config(self, '更新SMTP设置', 'smtp', _cfg)
                if err == TPE_OK:
                    # 同时更新内存缓存
                    get_cfg().sys.smtp.server = _server
                    get_cfg().sys.smtp.port = _port
                    get_cfg().sys.smtp.ssl = _ssl
                    get_cfg().sys.smtp.sender = _sender
                    # 特殊处理，防止前端拿到密码
                    get_cfg().sys_smtp_password = _password
                else:
                    return self.write_json(err)

            if 'password' in args:
                _cfg = args['password']
                _allow_reset = _cfg['allow_reset']
                _force_strong = _cfg['force_strong']
                _timeout = _cfg['timeout']
                err = system_model.save_config(self, '更新密码策略设置', 'password', _cfg)
                if err == TPE_OK:
                    get_cfg().sys.password.allow_reset = _allow_reset
                    get_cfg().sys.password.force_strong = _force_strong
                    get_cfg().sys.password.timeout = _timeout
                else:
                    return self.write_json(err)

            if 'login' in args:
                _cfg = args['login']
                _session_timeout = _cfg['session_timeout']
                _retry = _cfg['retry']
                _lock_timeout = _cfg['lock_timeout']
                _auth = _cfg['auth']
                err = system_model.save_config(self, '更新登录策略设置', 'login', _cfg)
                if err == TPE_OK:
                    get_cfg().sys.login.session_timeout = _session_timeout
                    get_cfg().sys.login.retry = _retry
                    get_cfg().sys.login.lock_timeout = _lock_timeout
                    get_cfg().sys.login.auth = _auth
                else:
                    return self.write_json(err)

            if 'storage' in args:
                _cfg = args['storage']
                _keep_log = _cfg['keep_log']
                _keep_record = _cfg['keep_record']
                _cleanup_hour = _cfg['cleanup_hour']
                _cleanup_minute = _cfg['cleanup_minute']
                err = system_model.save_config(self, '更新存储策略设置', 'storage', _cfg)
                if err == TPE_OK:
                    get_cfg().sys.storage.keep_log = _keep_log
                    get_cfg().sys.storage.keep_record = _keep_record
                    get_cfg().sys.storage.cleanup_hour = _cleanup_hour
                    get_cfg().sys.storage.cleanup_minute = _cleanup_minute
                else:
                    return self.write_json(err)

            return self.write_json(TPE_OK)
        except:
            log.e('\n')
            self.write_json(TPE_FAILED)


class DoSendTestMailHandler(TPBaseJsonHandler):
    @tornado.gen.coroutine
    def post(self):
        ret = self.check_privilege(TP_PRIVILEGE_SYS_CONFIG)
        if ret != TPE_OK:
            return

        args = self.get_argument('args', None)
        if args is None:
            return self.write_json(TPE_PARAM)
        try:
            args = json.loads(args)
        except:
            return self.write_json(TPE_JSON_FORMAT)

        try:
            _server = args['server']
            _port = int(args['port'])
            _ssl = args['ssl']
            _sender = args['sender']
            _password = args['password']
            _recipient = args['recipient']
        except:
            return self.write_json(TPE_PARAM)

        code, msg = yield mail.tp_send_mail(
            _recipient,
            '您好！\n\n这是一封测试邮件，仅用于验证系统的邮件发送模块工作是否正常。\n\n请忽略本邮件。',
            subject='测试邮件',
            sender='Teleport Server <{}>'.format(_sender),
            server=_server,
            port=_port,
            use_ssl=_ssl,
            username=_sender,
            password=_password
        )

        self.write_json(code, message=msg)


class DoCleanupStorageHandler(TPBaseJsonHandler):
    @tornado.gen.coroutine
    def post(self):
        ret = self.check_privilege(TP_PRIVILEGE_SYS_CONFIG)
        if ret != TPE_OK:
            return

        code, msg = yield record.cleanup_storage(self)

        self.write_json(code, data=msg)
