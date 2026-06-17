FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV HOSTNAME=sandbox
ENV UV_PROJECT_ENVIRONMENT="/venv"
ENV UV_LINK_MODE=copy

# 1.安装基础工具+OpenSSH Server
# mkdir /var/run/sshd 是SSH服务启动必须的目录
RUN apt-get update && apt-get install -y \
    ca-certificates git curl openssh-server \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/sshd

# 2.配置 SSH 的账户密码
# 2.1 关闭 DNS 反向解析 2.2.禁用多余认证/功能
RUN echo 'root:root' | chpasswd \
    && sed -i 's/^#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config \
    && sed -i 's/^UseDNS.*/UseDNS no/' /etc/ssh/sshd_config \
    && sed -i 's/^#GSSAPIAuthentication.*/GSSAPIAuthentication no/' /etc/ssh/sshd_config \
    && sed -i 's/^#ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config \
    && sed -i 's/^#LogLevel.*/LogLevel ERROR/' /etc/ssh/sshd_config

# 3.安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 4.设置下工作环境
WORKDIR /sandbox

# 5.预先配置环境，将基础依赖+Python版本同步到沙箱中并创建环境
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# 6.开放 SSH 端口（22）和应用端口（8080）
EXPOSE 22 8080

# 7.启动 SSH 服务(必须使用 -D 让它在前台运行，否则容器会推出)
CMD [ "/usr/sbin/sshd", "-D"]
