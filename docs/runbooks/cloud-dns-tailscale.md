# 阿里云 DNS 与 Tailscale 防火墙冲突

适用于已验证使用 eth0 与 100.100.2.136/138 的本任务服务器。DNS正确回包，但INPUT最前的ts-input会丢弃来自100.64.0.0/10的普通网卡回包。用限定来源/网卡/源端口/conntrack状态的四条规则解决，不切换DNS、不扩大CGNAT网段放行。

`scripts/ensure_cloud_dns.sh`幂等确保四条规则在INPUT最前；`remove`仅删除本脚本拥有的完整匹配规则。复用iptables与systemd oneshot/timer，每5秒检查一次，Tailscale重建规则后最多约6秒恢复顺序。短暂重配置窗口仍可能使一次DNS请求超时；不通过重启生产Tailscale或整机证明恢复。

先确认GitHub修复SHA和脚本哈希，并在服务器保存iptables-save、当前应用版本与被替换运维文件。安装位置：

- scripts/ensure_cloud_dns.sh → /usr/local/sbin/quantum-cloud-dns（0755）
- ops/systemd/quantum-cloud-dns.service → /etc/systemd/system/
- ops/systemd/quantum-cloud-dns.timer → /etc/systemd/system/

先systemd-analyze verify，再systemctl daemon-reload、systemctl start quantum-cloud-dns.service、systemctl enable --now quantum-cloud-dns.timer。保存本次Git SHA在/opt/ai-lab-shared/quantum-cloud-dns.sha；应用.deployed-sha不改。核对四条规则顺序，分别测试两个DNS的UDP/TCP解析、systemd解析与阿里云短信域名正常TLS，再调用一次正式短信API。HTTP200只证明接口已接受发送，不替代手机收件或六位码登录。

回滚：systemctl disable --now quantum-cloud-dns.timer，systemctl stop quantum-cloud-dns.service，执行/usr/local/sbin/quantum-cloud-dns remove，恢复备份运维文件（原不存在的本次文件删除），systemctl daemon-reload，恢复或移除quantum-cloud-dns.sha。不要直接iptables-restore整份快照覆盖其他任务后续规则。全面快照仅作灾难恢复，日常回滚只移除本任务四条规则。

本次规则顺序、幂等、Tailscale跳转被移到最前、完整限定范围及重复回滚由tests/test_cloud_dns_guard.py覆盖，使用测试目录中的iptables替身，不修改开发机防火墙。
