import os
import shutil
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import Optional, List, Dict, Union, Callable
from .base import DownloaderBase
from urllib.parse import urlparse, parse_qs
from markdownify import markdownify as md


class GithubDownloader(DownloaderBase):
    """GitHub资源下载器基类，提供GitHub仓库的解析和下载功能"""

    def __init__(self, url: str, output: str = None,
                 dingtalk_webhook: str = None, dingtalk_secret: str = None,
                 project_name: str = "Github项目更新监控",
                 only_latest: bool = True,
                 threads: int = 4,
                 log_file: str = None,
                 **kwargs):
        """初始化GitHub下载器

        Args:
            url: GitHub仓库URL
            output: 输出目录路径
            dingtalk_webhook: 钉钉webhook地址
            dingtalk_secret: 钉钉API的密钥
            only_latest: 只下载最新版本的
            threads: 下载线程
        """
        super().__init__(url, output,
                         dingtalk_webhook, dingtalk_secret,
                         project_name,
                         only_latest,
                         threads,
                         log_file,
                         **kwargs)
        self.github_output_path = os.path.join(self.output_path, 'github') if output is None else output
        self.logger.info(f"正在初始化GitHub下载器，URL: {kwargs.get('url')}")


    # 辅助解析tags页面，获取下一个页面的访问链接和链接中的after参数后的值（版本信息）
    def __get_next_page(self, soup: BeautifulSoup) -> Union[Dict[str, str], None]:
        """ 辅助解析tags页面，获取下一个tags页面的访问链接和after参数后的版本
        :return:
        {"url": "下一页的链接 (str)", "after_version": "下一个链接中显示的版本（str | None)"} | None

        ValueError:
            解析URL参数失败的时候
        """
        # 查找文本为"Next"的<a>标签
        next_link = soup.find('a', string='Next')

        if not next_link or not next_link.get('href'):
            self.logger.warning("⚠获取tags页面获取下一页访问链接失败，元素不存在")
            return None

        href = next_link['href']
        # 解析URL中的after参数
        parsed_url = urlparse(href)
        query_params = parse_qs(parsed_url.query)
        after_value = query_params.get('after', [""])[0] # 解析没有 after 参数的值的时候，返回 None

        if after_value:
            self.logger.info(f"下一页的访问URL: {urljoin(self.url, href)}")
            return {
                'url': urljoin(self.url, href),
                'after_version': after_value
            }
        else:
            self.logger.error("❌解析tagas页面，下一页URL参数 ?after=<version> 失败")
            raise ValueError("解析tagas页面，下一页URL参数 ?after=<version> 失败")

    # 辅助解析tags页面，获取版本信息和更新时间
    def __get_page_tags(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """

        :returns
            [
                {
                    "version": 版本 (str),
                    "update_time": 更新时间 (str),
                }
            ]
        """
        tags_box = []

        # 获取所有的tags标签 div
        self.logger.info("解析页面，获取版本信息和更新时间")

        all_divs = soup.find_all('div', class_='Box-row position-relative d-flex')

        if not all_divs:
            self.logger.error("❌解析tags页面，获取版本信息和更新时间失败")
            raise ValueError("解析tags页面，获取版本信息和更新时间失败")

        for div in all_divs:
            version = div.select('a', class_="Link--primary Link")[0].get_text(strip=True)
            update_time = div.select("relative-time")[0].get_text(strip=True)
            url = div.select('a', class_="Link--primary Link")[0].get('href')
            tags_box.append({"version": version, "update_time": update_time})
            self.logger.info(f"☺ 成功获取 {version} tag 信息, 此版本更新时间: {update_time}")

        return tags_box

    # 解析 tags 页面
    def _analysis_tag_page(self):
        """ 解析 tag 标签页面 ，获取版当页显示的本信息

        :returns
            [
                {“version": "",  "update_time": ""},
            ]
        """
        result = []

        # 请求第一个tags页面
        try:
            response = requests.get(urljoin(self.url, "tags"), **self.kwargs)
            response.raise_for_status()


            soup = BeautifulSoup(response.text, 'html.parser')

            # 没有tags页面
            if 'There aren’t any releases here' in soup.text:
                self.logger.warning("⚠ 不存在tags页面")
                return []

            # 无论如何先解析第一页，获取所有的版本
            first_page_tags = self.__get_page_tags(soup)
            first_page_oldest_version = first_page_tags[-1]['version'] # 获取第一页的最后一个版本名称
            next_page_info = self.__get_next_page(soup) # 下一页的版本信息和访问链接

            if self.only_latest:
                self.logger.info("只获取最新的版本")
                result.append({"version": first_page_tags[0]['version'], "update_time":  first_page_tags[0]['update_time']})
                return result
            # 如果没有找到导航链接，说明只有1页
            elif next_page_info is None:
                self.logger.info("tags 只有1页")
                result.extend(first_page_oldest_version)
                return result
            else:
                self.logger.info("tags 存在多页")
                # 首页肯定是相等的
                next_after_version = next_page_info['after_version']
                current_page_oldest_version = first_page_oldest_version

                # 循环获取下一页的数据，直到此页最后一个版本和 after=版本 的值不相同
                while next_after_version == current_page_oldest_version:
                    self.logger.info(f"访问 tags 页面: {next_page_info['url']}")
                    # 访问下一页
                    next_page_request = requests.get(next_page_info['url'], **self.kwargs)
                    # 解析页面
                    next_page_soup = BeautifulSoup(next_page_request.content, 'html.parser')
                    # 获取所有版本信息
                    next_page_tags = self.__get_page_tags(next_page_soup)
                    # 记录版本信息
                    result.extend(next_page_tags)
                    # 更新访问信息
                    current_page_oldest_version = next_page_tags[-1]['version'] # 获取第一页的最后一个版本名称
                    next_after_version = self.__get_next_page(next_page_soup) # 下一页的下一页版本信息和访问链接
                return result
        except Exception as e:
            self.logger.error(f"解析 tags 页面失败: {urljoin(self.url, 'tags')}, 错误信息: {str(e)}")
            raise

    # 解析主页面
    def _analysis_main_page(self, version: Optional[str] = None) -> Dict[str, str]:
        """ 解析主页面

        :returns
            {"source": "源码下载链接", "about": "about (str)", "exists_release": 是否存在 release (bool), "commit_time": "最后一次 commit时间"}

        ValueError:
            获取commit失败 / 获取 about 信息失败
        """

        if version:
            main_page_url = urljoin(self.url, f"tree/{version}")
        else:
            main_page_url = self.url

        self.logger.info(f"访问版本: {version if version else 'latest'}")
        self.logger.info(f"访问URL: {main_page_url}")

        try:
            main_response = requests.get(main_page_url, **self.kwargs)
            main_response.raise_for_status()
        except Exception as e:
            self.logger.error(f"❌请求主页面失败: {str(e)}")
            self._send_other_msg(title=f'访问{self.project_name}主页失败', message=f"URL: {main_page_url if self.url else '未填写项目URL'}， 版本: {version if version else 'latest'}, 错误信息: {str(e)}", msg_type='error')
            raise

        try:
            # 解析主页面
            soup = BeautifulSoup(main_response.text, 'html.parser')

            # 首先获取右上角的分支/版本名称
            branches_tags_name = soup.find('div', class_='Layout-main').find('button').get_text(strip=True)
            self.logger.info("解析主页面分支/tags名称: " + branches_tags_name)
            if not branches_tags_name:
                self.logger.error("解析失败")
                raise ValueError("解析主页面分支/tags名称失败")
        except Exception as e:
            self._send_other_msg(title=f'解析{self.project_name}主页失败', message=f"解析主页面分支/tags名称失败， 版本: {version if version else 'latest'}, 错误信息: {str(e)}", msg_type='error')
            raise

        source_zip = None
        # 包含了main的情况, 或者链接就是 /tree/ 分支
        if branches_tags_name:
            source_zip = urljoin(self.url, f"archive/refs/heads/{branches_tags_name}.zip")

        # 未指定 version，且访问的是 /tree/ 的不同版本的页面
        if '/tree/' in self.url and not version:
            version = branches_tags_name

        # 如果指定了下载的版本version
        if version:
            source_zip = urljoin(self.url, f"archive/refs/tags/{version}.zip")

        # 这一顿操作，必然存在 source_zip ,
        self.logger.info(f"源码zip包URL: {source_zip}")

        if not source_zip:
            self.logger.error("❌获取源码zip包URL失败！！！")
            raise ValueError("获取源码zip包URL失败！！！")

        # 请求获取请最后的提交时间 (主页面显示的最近的更新的时间) 而不是这个版本更新的时间:
        try:
            commit_kwargs = self.kwargs.copy()
            commit_kwargs['headers']['content-type'] = "application/json"
            commit_kwargs['headers']['content-encoding'] = "gzip"
            commit_kwargs['headers']['cookie'] = "tz=Asia%2FShanghai"
            commit_kwargs['headers']['accept'] = "application/json"
            commit_kwargs['headers']['accept-language'] = "zh-CN,zh;q=0.9"

            commit_response = requests.get(urljoin(self.url, f"latest-commit/{branches_tags_name}"), **commit_kwargs)
            commit_response.raise_for_status()

            if commit_response.status_code == 200:
                commit_time = commit_response.json()['date']
            else:
                self.logger.error(f"❌获取main主页的commit更新时间错误, 状态码: {commit_response.status_code}")
                raise ValueError("自己抛出异常，状态码不为 200")
            self.logger.info(f"最后一次commit时间: {commit_time}")

            # 重新把设置的归为原本的，
            self.kwargs['headers']['content-type'] = None
            self.kwargs['headers']['content-encoding'] = None
            self.kwargs['headers']['cookie'] = None
            self.kwargs['headers']['accept'] = None
            self.kwargs['headers']['accept-language'] = None
        except Exception as e:
            self.logger.error(f"❌获取main主页的 commit 更新时间错误: {str(e)}")
            self._send_other_msg(title=f'解析{self.project_name}主页失败', message=f"获取main主页的 commit 更新时间错误， 版本: {version if version else 'latest'}", msg_type='error')
            raise

        # 解析 about 信息
        try:
            about_text = soup.select('p.f4.my-3')[0].text.strip()
            self.logger.debug(f"获取到的项目描述信息: {about_text[:50]}...")

            # 为什么不获取对应的 访问链接，应为不同版显示的都是最新的版本的链接，所以不获取
            exists_release = bool(soup.find('div', class_="ml-2 min-width-0"))
            self.logger.info(f"{'✅存在' if exists_release else '⚠不存在'}release页面")
        except Exception as e:
            self.logger.error(f"❌获取项目描述信息失败: {e}")

            raise ValueError(f"获取项目about信息失败: {str(e)}")

        # 获取文件名（优先使用head方法/然后失败自动使用从URL中获取文件名）
        file_name = self.get_filename_from_response(source_zip)
        if not file_name:
            self.logger.error("❌main页面获取源码文件名失败")
            raise ValueError("main页面获取源码文件名失败")

        return {
            "file_name": file_name,    #从响应中获取文件名称
            "source": source_zip,
            "about": about_text,
            "exists_release": exists_release,
            "commit_time": commit_time,
        }

    # 解析对应版本的 release 页面
    def _analysis_release_page(self, version: str) -> Dict[str, Union[str, List[Dict[str, str]]]]:
        """ 解析 version 对应的 release 页面

        :returns
        {
            "file_version": "版本",
            "change": "版本更新变化",
            "data": [
                {
                    "file_name": "文件名称 (str)",
                    "file_hash": "文件hash (str)",
                    "file_url": "下载URL (str)",
                    "update_time": "(更新的时间) (str)",
                    "source_code": "是否为源码 (bool),
                },
            ]
        }
        """
        result = {}
        # 版本变化描述
        change_markdown = ""
        release_tag_url = urljoin(self.url, f"releases/tag/{version}")

        try:
            release_response = requests.get(release_tag_url, **self.kwargs)
            release_page_soup = BeautifulSoup(release_response.text, 'html.parser')
            change = release_page_soup.find('div', {'data-view-component': 'true', 'class': 'Box-body'})

            if not change:
                self.logger.info(f"⚠版本{version}没有编写版本变化描述")
                self.logger.debug(f"查看确认URL: {release_tag_url} 是否正确，状态码： {release_response.status_code}")
            else:
                # 转为markdown
                change_markdown = md(html=str(change))
        except requests.exceptions as e:
            self.logger.error(f"❌获取版本变化信息失败: {str(e)}")
            self._send_other_msg(title=f'访问{self.project_name}项目 release 页面失败', message=f"URL: {release_tag_url}, 版本: {version}, 错误信息: {str(e)}", msg_type='error')
            raise

        # 获取所有的下载信息
        assets_url = urljoin(self.url, f"releases/expanded_assets/{version}")

        try:
            # 获取版本下载URL
            download_response = requests.get(assets_url, **self.kwargs)
            download_response.raise_for_status()

            assets_soup = BeautifulSoup(download_response.text, 'html.parser')
            # 获取每一个存储文件名 / 下载链接 /hash / 文件大小 / 更新日期
            all_li = assets_soup.find_all('li')

            data_list = []
            for li in all_li:
                file_name = li.find('span', class_='Truncate-text text-bold').get_text(strip=True)
                if file_name != 'Source code':
                    file_url = "https://github.com" + li.find('span', class_='Truncate-text text-bold').parent.get('href')
                    file_hash = "" if not li.find('span', class_='Truncate text-mono text-small color-fg-muted') else li.find('span', class_='Truncate text-mono text-small color-fg-muted').get_text(strip=True)
                    update_time = li.find('relative-time').get('datetime')
                    data_list.append({"file_name": file_name, "file_hash": file_hash if file_hash else "", "update_time": update_time, "file_url": file_url, "source_code": False})
                    self.logger.info(f"获取 {file_name}, 更新时间: {update_time}, 下载URL: {file_url}, 文件hash: {file_hash if file_hash else '无'}")
            self.logger.debug(f"为版本 {version} 找到 {len(data_list)} 个下载URL")

            result['file_version'] = version
            result['change'] = change_markdown
            result["data"] = data_list

            return result
        except Exception as e:
            self._send_other_msg(title=f'解析{self.project_name}项目 release 页面失败', message=f"URL: {release_tag_url}, 版本: {version}, 错误信息: {str(e)}", msg_type='error')
            raise

    # 获取下载信息
    def request(self) -> List[Dict[str, Union[str, List[Dict[str, str]]]]]:
        """ 获取Github所有的下载信息 (源码、release）

        :return:
        [
            {
                "file_version": "版本",
                "change": "版本更新变化",
                "data": [
                    {
                        "file_name": "文件名称 (str)",
                        "file_hash": "文件hash (str)",
                        "file_url": "下载URL (str)",
                        "update_time": "(更新的时间) (str)",
                        "source_code": "是否为源码 (bool),
                    },
                ]
            }
        ]
        """
        result = []
        # 请求主页面
        main_page_info = self._analysis_main_page()
        if not main_page_info['exists_release']:
            return [{"file_version": "latest",
                     "about": main_page_info['about'],
                     "change": "",
                     "data": [
                         {
                             "file_name": main_page_info['file_name'],
                             "file_hash": "",
                             "file_url": main_page_info['source'],
                             "update_time": main_page_info['commit_time'],
                             "source_code": True
                         }
                     ]}]
        # 存在 release 页面
        else:
            # 获取所有的版本信息（已在内部实现了只获取最新的版本)
            tags_info = self._analysis_tag_page()
            # 遍历所有 tag 获取时间/版本
            for tag in tags_info:
                # 前往的版本
                go_version = tag['version']

                # 解析对应版本主页面
                go_version_main_page_info = self._analysis_main_page(version=go_version)

                if not go_version_main_page_info['exists_release']:
                    result.append({"file_version": "latest",
                                   "about": go_version_main_page_info['about'],
                                   "change": "",
                                   "data": [
                                       {
                                           "file_name": go_version_main_page_info['file_name'],
                                           "file_hash": "",
                                           "file_url": go_version_main_page_info['source'],
                                           "update_time": go_version_main_page_info['commit_time'],
                                           "source_code": True
                                       }
                                   ]})
                else:
                    # 前往 release页面
                    release_info = self._analysis_release_page(version=go_version)
                    result.append({"file_version": release_info['file_version'],
                                   "about": go_version_main_page_info['about'],
                                   "change": release_info['change'],
                                   "data": release_info['data'] + [{
                                       "file_name": go_version_main_page_info['file_name'],
                                       "file_hash": "",
                                       "file_url": go_version_main_page_info['source'],
                                       "update_time": go_version_main_page_info['commit_time'],
                                       "source_code": True
                                   }]})

            return result

    # 重写输出
    def download(self, version_information: List[Dict[str, Union[str, List[Dict[str, str]]]]]) -> None:
        """信息列表中的文件下载，分类输出。

        Parameters
        ----------
        version_information : List[Dict[str, List[Dict[str, str]]]]
        下载信息列表，约定传入的格式为：
        [
            {
                "file_version": "" (str),
                "about": "工具描述信息",
                "change": "版本更新变化",
                "data": [{ "file_name": "文件名称 (str)", "file_hash": "文件hash (str)", "file_url": "下载URL (str)", "update_time": "(更新的时间) (str)", "source_code": "是否源码 (bool)"}]
            }
        ]

        输出路径，如果不指定就使用类中指定的 self.github_output_path/version路径，否则就是指定的路径
        """
        # 存储源文件
        self._output_download(version_information=version_information, threads=self.threads,)


    # 检测hash值是否符合预期
    def check_file(self, file_path, file_hash) -> bool:
        file_hash = file_hash.replace("sha256:", "")
        return self.verify_hash(file_path=file_path, file_hash=file_hash, hash_type='sha256')

    # 过滤
    def filter(self, version_information: List[Dict[str, Union[str, List[Dict[str, str]]]]], *args, **kwargs) -> List[Dict[str, Union[str, List[Dict[str, str]]]]]:
        pass
