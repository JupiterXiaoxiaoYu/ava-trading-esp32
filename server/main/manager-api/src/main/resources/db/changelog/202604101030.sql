UPDATE `sys_params`
SET `param_value` = '315360000'
WHERE `param_code` = 'close_connection_no_voice_time';

INSERT INTO `sys_params` (id, param_code, param_value, value_type, param_type, remark)
SELECT 313, 'close_connection_no_voice_time', '315360000', 'number', 1, '无语音输入断开连接时间(秒)'
WHERE NOT EXISTS (
  SELECT 1 FROM `sys_params` WHERE `param_code` = 'close_connection_no_voice_time'
);

UPDATE `sys_params`
SET `param_value` = 'true'
WHERE `param_code` = 'enable_websocket_ping';

INSERT INTO `sys_params` (id, param_code, param_value, value_type, param_type, remark)
SELECT 314, 'enable_websocket_ping', 'true', 'boolean', 1, '是否启用WebSocket心跳保活机制'
WHERE NOT EXISTS (
  SELECT 1 FROM `sys_params` WHERE `param_code` = 'enable_websocket_ping'
);
