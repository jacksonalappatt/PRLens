"""Azure DevOps API Client for Pull Request management."""

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class AdoClient:
    def __init__(self, org: str, project: str, pat: Optional[str] = None):
        self.org = org
        self.project = project
        self.pat = (
            pat
            or os.environ.get("AZURE_DEVOPS_PAT")
            or os.environ.get("ADO_PAT")
            or os.environ.get("AZURE_DEVOPS_EXT_PAT")
        )
        if not self.pat:
            raise ValueError(
                "No Azure DevOps PAT found in environment variables (AZURE_DEVOPS_PAT, ADO_PAT, AZURE_DEVOPS_EXT_PAT)."
            )
        self._user_info: Optional[Dict[str, Any]] = None
        self._team_membership_cache: Dict[str, bool] = {}

    def _request(self, url: str, method: str = "GET", body: Optional[dict] = None) -> Any:
        encoded_pat = base64.b64encode(f":{self.pat}".encode("ascii")).decode("ascii")
        headers = {
            "Authorization": f"Basic {encoded_pat}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as response:
                content = response.read().decode("utf-8")
                return json.loads(content) if content else {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            print(f"[AdoClient Error {e.code}] {e.reason}: {error_body}", file=sys.stderr)
            raise

    def get_current_user_info(self) -> Dict[str, Any]:
        if self._user_info:
            return self._user_info
        url = f"https://dev.azure.com/{self.org}/_apis/connectionData?api-version=7.1-preview.1"
        res = self._request(url)
        user = res.get("authenticatedUser", {})
        self._user_info = {
            "id": user.get("id"),
            "displayName": user.get("providerDisplayName") or user.get("customDisplayName"),
            "uniqueName": user.get("user"),
        }
        return self._user_info

    def check_user_in_team(self, team_id: str, user_id: str, project: Optional[str] = None) -> bool:
        proj = project or self.project
        cache_key = f"{proj}:{team_id}"
        if cache_key in self._team_membership_cache:
            return self._team_membership_cache[cache_key]

        url = (
            f"https://dev.azure.com/{self.org}/_apis/projects/{proj}/teams/{team_id}/members?api-version=7.1-preview.2"
        )
        try:
            res = self._request(url)
            members = res.get("value", [])
            in_team = any(m.get("identity", {}).get("id") == user_id for m in members)
            self._team_membership_cache[cache_key] = in_team
            return in_team
        except Exception:
            self._team_membership_cache[cache_key] = False
            return False

    def get_assigned_unreviewed_prs(self, repo_id: Optional[str] = None) -> List[Dict[str, Any]]:
        user_info = self.get_current_user_info()
        user_id = user_info["id"]

        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/git/pullrequests?searchCriteria.status=active&api-version=7.1-preview.1"
        try:
            res = self._request(url)
            prs = res.get("value", [])
        except Exception as e:
            print(f"[AdoClient] Error fetching active PRs: {e}", file=sys.stderr)
            return []

        unreviewed = []
        for pr in prs:
            if pr.get("isDraft", False):
                continue

            merge_status = str(pr.get("mergeStatus", "")).lower()
            if merge_status == "conflicts" or pr.get("hasConflicts", False):
                continue

            # If repo_id specified, filter for matching repository
            if repo_id:
                pr_repo_name = pr.get("repository", {}).get("name", "")
                pr_repo_id = pr.get("repository", {}).get("id", "")
                if pr_repo_name.lower() != repo_id.lower() and pr_repo_id.lower() != repo_id.lower():
                    continue

            reviewers = pr.get("reviewers", [])
            user_reviewer = None
            user_teams_matched = []

            for r in reviewers:
                r_id = r.get("id")
                if r_id == user_id:
                    user_reviewer = r
                elif r.get("isContainer", False):
                    pr_project = pr.get("repository", {}).get("project", {}).get("name") or self.project
                    if self.check_user_in_team(r_id, user_id, pr_project):
                        user_teams_matched.append(r)

            if not user_reviewer and not user_teams_matched:
                continue

            user_vote = user_reviewer.get("vote", 0) if user_reviewer else 0
            if user_reviewer and user_vote != 0:
                continue

            if (
                user_teams_matched
                and all(r.get("vote", 0) != 0 for r in user_teams_matched)
                and not (user_reviewer and user_vote == 0)
            ):
                continue

            unreviewed.append(
                {
                    "pr_id": pr.get("pullRequestId"),
                    "title": pr.get("title"),
                    "description": pr.get("description", ""),
                    "createdBy": pr.get("createdBy", {}).get("displayName"),
                    "creationDate": pr.get("creationDate"),
                    "repository": pr.get("repository", {}).get("name"),
                    "repositoryId": pr.get("repository", {}).get("id"),
                    "project": pr.get("repository", {}).get("project", {}).get("name") or self.project,
                    "sourceBranch": pr.get("sourceRefName"),
                    "targetBranch": pr.get("targetRefName"),
                    "isDraft": pr.get("isDraft", False),
                    "mergeStatus": pr.get("mergeStatus"),
                    "assignedDirectly": user_reviewer is not None,
                    "assignedTeams": [t.get("displayName") for t in user_teams_matched],
                    "url": pr.get("url"),
                    "webUrl": f"https://dev.azure.com/{self.project}/_git/{pr.get('repository', {}).get('name')}/pullrequest/{pr.get('pullRequestId')}",
                }
            )

        return unreviewed

    def get_pr_details(self, repo_id: str, pr_id: int) -> Dict[str, Any]:
        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/git/repositories/{repo_id}/pullRequests/{pr_id}?api-version=7.1-preview.1"
        return self._request(url)

    def post_comment(
        self,
        repo_id: str,
        pr_id: int,
        comment_text: str,
        file_path: Optional[str] = None,
        line_num: Optional[int] = None,
    ) -> Dict[str, Any]:
        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/git/repositories/{repo_id}/pullRequests/{pr_id}/threads?api-version=7.1-preview.1"
        body: Dict[str, Any] = {
            "comments": [{"parentCommentId": 0, "content": comment_text, "commentType": 1}],
            "status": 1,
        }
        if file_path and line_num:
            body["threadContext"] = {
                "filePath": file_path,
                "rightFileStart": {"line": line_num, "offset": 1},
                "rightFileEnd": {"line": line_num, "offset": 1},
            }
        return self._request(url, method="POST", body=body)

    def set_vote(self, repo_id: str, pr_id: int, vote: int) -> Dict[str, Any]:
        user_info = self.get_current_user_info()
        user_id = user_info["id"]
        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/git/repositories/{repo_id}/pullRequests/{pr_id}/reviewers/{user_id}?api-version=7.1-preview.1"
        return self._request(url, method="PUT", body={"vote": vote})
