FROM ubuntu:22.04

# 2.安装过程中避免交互式提示并设置主机名
ENV DEBIAN_FRONTEND=noninteractive
ENV HOSTNAME=sandbox

# 3.将 ubuntu 默认的 apt 软件源地址统一换成 aliyun mirrors
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list \
    && sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list \
    && sed -i 's|http://ports.ubuntu.com/ubuntu-ports/|http://mirrors.aliyun.com/ubuntu-ports/|g' /etc/apt/sources.list

# 4.更新和安装基础软件后移除依赖 \
RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo bc curl wget gnupg software-properties-common supervisor \
    xterm socat xvfb x11vnc websockify \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 5. 创建 ubuntu 用户并赋予 sudo 权限
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

# 6.安装 python3.10 版本(非 uv)
RUN add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.10 python3.10-venv python3.10-dev python3-pip && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 7.为pip3配置阿里云镜像源
RUN pip3 config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# 8.安装 node.js 24.12.0 版本(lts)
RUN mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main" >> /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 9.将 npm 镜像设置为阿里云镜像
RUN npm config set registry https://registry.npmmirror.com

# 10.安装 Chromium 浏览器
RUN add-apt-repository ppa:xtradeb/apps -y && \
    apt-get update && \
    apt-get install -y chromium --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 11.安装中文字体支持
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    language-pack-zh-hans \
    locales \
    && locale-gen zh_CN.UTF-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 12.设置默认编码
ENV LANG=zh_CN.UTF-8 \
    LANGUAGE=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8


# 10.设置工作空间
WORKDIR /sandbox

# 11.拷贝项目依赖文件到工作空间
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 12.拷贝整个项目文件
COPY . .

# 13.将 supervisord.conf 拷贝 supervisor 服务的配置目录中
COPY supervisord.conf /etc/supervisor/conf.d/sandbox.conf

# 14.暴露端口
EXPOSE 8080 9222 5900 5901

# 15.额外的环境变量
ENV CHROME_ARGS=""
ENV UVI_ARGS=""

# 16.使用 supervisor 管理所有进程
CMD ["supervisord", "-n", "-c", "/sandbox/supervisord.conf"]
