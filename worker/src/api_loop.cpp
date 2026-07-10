#include <array>
#include <cctype>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#include <direct.h>
#define POPEN _popen
#define PCLOSE _pclose
#define GETCWD _getcwd
#else
#include <unistd.h>
#define POPEN popen
#define PCLOSE pclose
#define GETCWD getcwd
#endif

#ifndef AV_IMGDATA_WORKER_VERSION
#define AV_IMGDATA_WORKER_VERSION "0.1.0-phase-h1"
#endif

namespace {

struct CommandResult { int exit_code = -1; std::string output; std::string command; };
struct LoopConfig {
    std::string config_path, config_dir, worker_id, worker_bin, api_url, token_file;
    std::string workspace_root, path_base_dir;
    int poll_interval_seconds = 2;
};
struct LocalJobResult { bool ok = false; std::string job_json, code, message, resolved_path; };

std::string arg_value(const std::vector<std::string>& args, const std::string& name) {
    for (std::size_t i = 0; i + 1 < args.size(); ++i) if (args[i] == name) return args[i + 1];
    return "";
}
bool has_arg(const std::vector<std::string>& args, const std::string& name) {
    for (const auto& arg : args) if (arg == name) return true;
    return false;
}
int parse_int(const std::string& value, int fallback) {
    if (value.empty()) return fallback;
    char* end = nullptr; const long parsed = std::strtol(value.c_str(), &end, 10);
    return end == value.c_str() ? fallback : static_cast<int>(parsed);
}
int normalized_exit_code(int raw) {
#ifndef _WIN32
    if (raw >= 256 && raw % 256 == 0) return raw / 256;
#endif
    return raw;
}
bool is_sep(char c) { return c == '/' || c == '\\'; }
bool looks_absolute(const std::string& path) {
    return !path.empty() && ((path.size() >= 2 && path[1] == ':') || is_sep(path[0]));
}
std::string dirname_of(const std::string& path) {
    const auto pos = path.find_last_of("/\\");
    if (pos == std::string::npos) return ".";
    return pos == 0 ? path.substr(0, 1) : path.substr(0, pos);
}
std::string join_path(const std::string& base, const std::string& path) {
    if (path.empty() || looks_absolute(path)) return path;
    if (base.empty() || base == ".") return path;
#ifdef _WIN32
    const char sep = '\\';
#else
    const char sep = base.find('\\') != std::string::npos ? '\\' : '/';
#endif
    return is_sep(base.back()) ? base + path : base + sep + path;
}
std::string cwd() {
    std::array<char, 4096> buffer{};
    return GETCWD(buffer.data(), static_cast<int>(buffer.size())) ? std::string(buffer.data()) : ".";
}
char preferred_sep(const std::string& path) {
#ifdef _WIN32
    (void)path; return '\\';
#else
    return path.find('\\') != std::string::npos ? '\\' : '/';
#endif
}
std::string normalize_path(const std::string& path) {
    if (path.empty()) return path;
    const char sep = preferred_sep(path);
    std::string value = path; for (char& c : value) if (is_sep(c)) c = sep;
    std::string prefix; std::size_t pos = 0; bool absolute = false;
    if (value.size() >= 2 && value[1] == ':') { prefix = value.substr(0, 2); pos = 2; if (pos < value.size() && value[pos] == sep) { prefix += sep; ++pos; absolute = true; } }
    else if (value.size() >= 2 && value[0] == sep && value[1] == sep) { prefix = std::string(2, sep); pos = 2; absolute = true; }
    else if (value[0] == sep) { prefix = std::string(1, sep); pos = 1; absolute = true; }
    std::vector<std::string> parts;
    while (pos <= value.size()) {
        const auto next = value.find(sep, pos);
        const std::string part = value.substr(pos, next == std::string::npos ? std::string::npos : next - pos);
        if (part.empty() || part == ".") {}
        else if (part == "..") { if (!parts.empty() && parts.back() != "..") parts.pop_back(); else if (!absolute) parts.push_back(part); }
        else parts.push_back(part);
        if (next == std::string::npos) break;
        pos = next + 1;
    }
    std::string out = prefix;
    for (const auto& part : parts) { if (!out.empty() && out.back() != sep) out += sep; out += part; }
    return out.empty() ? "." : out;
}
std::string absolute_path(const std::string& path) { return normalize_path(looks_absolute(path) ? path : join_path(cwd(), path)); }
bool file_exists(const std::string& path) { std::ifstream f(path.c_str(), std::ios::binary); return !path.empty() && static_cast<bool>(f); }
std::string shell_quote(const std::string& value) {
#ifdef _WIN32
    std::string out = "\""; for (char c : value) out += c == '"' ? "\\\"" : std::string(1, c); return out + "\"";
#else
    std::string out = "'"; for (char c : value) out += c == '\'' ? "'\\''" : std::string(1, c); return out + "'";
#endif
}
bool ensure_dir(const std::string& path) {
#ifdef _WIN32
    return std::system(("mkdir " + shell_quote(normalize_path(path)) + " >NUL 2>NUL").c_str()) == 0;
#else
    return std::system(("mkdir -p " + shell_quote(normalize_path(path))).c_str()) == 0;
#endif
}
std::string read_file(const std::string& path) { std::ifstream in(path.c_str(), std::ios::binary); std::ostringstream b; b << in.rdbuf(); return b.str(); }
bool write_file(const std::string& path, const std::string& text) { ensure_dir(dirname_of(path)); std::ofstream out(path.c_str(), std::ios::binary); out << text; return static_cast<bool>(out); }
std::string trim(std::string value) { while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) value.pop_back(); std::size_t n=0; while(n<value.size()&&std::isspace(static_cast<unsigned char>(value[n])))++n; return value.substr(n); }
std::string abbreviate(const std::string& value, std::size_t n) { return value.size() <= n ? value : value.substr(0, n > 3 ? n - 3 : n) + (n > 3 ? "..." : ""); }
std::string json_escape(const std::string& value) { std::ostringstream out; for(char c:value){ switch(c){case '\\':out<<"\\\\";break;case '"':out<<"\\\"";break;case '\n':out<<"\\n";break;case '\r':out<<"\\r";break;case '\t':out<<"\\t";break;default:out<<c;}} return out.str(); }
CommandResult run_command(const std::string& command) { CommandResult r; r.command=command; std::array<char,512>b{}; FILE* p=POPEN(command.c_str(),"r"); if(!p){r.output="popen_failed";return r;} while(fgets(b.data(),static_cast<int>(b.size()),p))r.output+=b.data(); r.exit_code=PCLOSE(p); r.output=trim(r.output); return r; }

std::string extract_json_string(const std::string& json, const std::string& key) {
    const std::string needle="\""+key+"\""; auto pos=json.find(needle); if(pos==std::string::npos)return ""; pos=json.find(':',pos+needle.size()); if(pos==std::string::npos)return ""; pos=json.find('"',pos+1); if(pos==std::string::npos)return ""; ++pos; std::string value; bool esc=false;
    for(;pos<json.size();++pos){char c=json[pos]; if(esc){switch(c){case'n':value+='\n';break;case'r':value+='\r';break;case't':value+='\t';break;default:value+=c;}esc=false;}else if(c=='\\')esc=true;else if(c=='"')break;else value+=c;} return value;
}
std::string extract_block(const std::string& json,const std::string& key,char open,char close){const std::string needle="\""+key+"\"";auto pos=json.find(needle);if(pos==std::string::npos)return"";pos=json.find(open,pos+needle.size());if(pos==std::string::npos)return"";int depth=0;bool str=false,esc=false;for(std::size_t i=pos;i<json.size();++i){char c=json[i];if(esc){esc=false;continue;}if(c=='\\'){esc=true;continue;}if(c=='"'){str=!str;continue;}if(str)continue;if(c==open)++depth;else if(c==close&&--depth==0)return json.substr(pos,i-pos+1);}return"";}
std::string extract_object(const std::string& json,const std::string& key){return extract_block(json,key,'{','}');}
std::string normalize_url(std::string url){while(!url.empty()&&url.back()=='/')url.pop_back();return url;}
std::string read_token(const std::string& path){return trim(read_file(path));}

bool safe_relative_path(const std::string& value, std::string* normalized, std::string* error) {
    if (value.empty()) { *error = "local_path_missing"; return false; }
    if (looks_absolute(value)) { *error = "local_path_must_be_relative"; return false; }
    std::string portable=value; for(char& c:portable) if(c=='\\') c='/';
    std::vector<std::string> parts; std::size_t pos=0;
    while(pos<=portable.size()) { auto next=portable.find('/',pos); std::string part=portable.substr(pos,next==std::string::npos?std::string::npos:next-pos); if(part.empty()||part=="."){} else if(part=="..") { *error="local_path_escape"; return false; } else parts.push_back(part); if(next==std::string::npos)break; pos=next+1; }
    if(parts.empty()){*error="local_path_empty";return false;}
    std::ostringstream out; for(std::size_t i=0;i<parts.size();++i){if(i)out<<'/';out<<parts[i];} *normalized=out.str(); return true;
}
bool replace_json_string(std::string* json,const std::string& key,const std::string& value){const std::string needle="\""+key+"\"";auto pos=json->find(needle);if(pos==std::string::npos)return false;pos=json->find(':',pos+needle.size());if(pos==std::string::npos)return false;auto q=json->find('"',pos+1);if(q==std::string::npos)return false;auto end=q+1;bool esc=false;for(;end<json->size();++end){char c=(*json)[end];if(esc)esc=false;else if(c=='\\')esc=true;else if(c=='"')break;}if(end>=json->size())return false;json->replace(q+1,end-q-1,json_escape(value));return true;}
LoopConfig parse_config(const std::string& path,const std::string& json,const std::vector<std::string>& args){LoopConfig c;c.config_path=absolute_path(path);c.config_dir=dirname_of(c.config_path);c.worker_id=extract_json_string(json,"worker_id");c.workspace_root=absolute_path(join_path(c.config_dir,extract_json_string(json,"workspace_root")));c.path_base_dir=arg_value(args,"--path-base-dir");if(c.path_base_dir.empty())c.path_base_dir=extract_json_string(json,"path_base_dir");if(c.path_base_dir.empty())c.path_base_dir=cwd();c.path_base_dir=absolute_path(c.path_base_dir);c.poll_interval_seconds=parse_int(extract_json_string(json,"poll_interval_seconds"),2);if(c.poll_interval_seconds<1)c.poll_interval_seconds=1;const std::string auth=extract_object(json,"auth");const std::string configured_token=extract_json_string(auth.empty()?json:auth,"token_file");c.token_file=absolute_path(join_path(c.config_dir,configured_token.empty()?"../worker.token":configured_token));c.api_url=arg_value(args,"--api-url");if(c.api_url.empty())c.api_url=extract_json_string(json,"worker_api_base_url");if(c.api_url.empty()){auto base=extract_json_string(json,"dsm_base_url");if(!base.empty())c.api_url=normalize_url(base)+"/worker-api";}c.api_url=normalize_url(c.api_url);c.worker_bin=arg_value(args,"--worker-bin");if(c.worker_bin.empty()){
#ifdef _WIN32
c.worker_bin=join_path(c.config_dir,"../bin/av-imgdata-worker.exe");
#else
c.worker_bin=join_path(c.config_dir,"../bin/av-imgdata-worker");
#endif
}c.worker_bin=absolute_path(c.worker_bin);return c;}
std::string capabilities_json(){return "[\"face_native_detect\",\"face_native_embed\",\"face_native_detect_batch\",\"face_native_embed_batch\",\"face_native_rank_embeddings\",\"face_native_profile_math\",\"warm_processor_worker\",\"input_shared_path\"]";}
std::string api_post(const LoopConfig& c,const std::string& action,const std::string& token,const std::string& body){auto body_path=normalize_path(join_path(c.workspace_root,".api-"+action+"-request.json"));write_file(body_path,body);std::string cmd="curl -sS -X POST -H "+shell_quote("Content-Type: application/json")+" -H "+shell_quote("Authorization: Bearer "+token)+" --data-binary @"+shell_quote(body_path)+" "+shell_quote(c.api_url+"/"+action)+" 2>&1";auto r=run_command(cmd);return normalized_exit_code(r.exit_code)==0?r.output:"{\"status\":\"error\",\"code\":\"curl_failed\",\"message\":\""+json_escape(r.output)+"\"}";}
std::string heartbeat_body(const LoopConfig& c,const std::string& status){return "{\"worker_id\":\""+json_escape(c.worker_id)+"\",\"version\":\""+AV_IMGDATA_WORKER_VERSION+"\",\"status\":\""+status+"\",\"capabilities\":"+capabilities_json()+",\"metadata\":{\"runtime\":\"cxx-api-loop\",\"path_base_dir\":\""+json_escape(c.path_base_dir)+"\",\"input_modes\":[\"shared_path\"]}}";}
std::string claim_body(const LoopConfig& c){return "{\"worker_id\":\""+json_escape(c.worker_id)+"\",\"capabilities\":"+capabilities_json()+"}";}
LocalJobResult make_local_job(const std::string& claimed,const LoopConfig& c){LocalJobResult r;std::string payload=extract_object(claimed,"payload");const std::string mode=extract_json_string(payload,"input_mode");if(mode!="shared_path"){r.code="unsupported_input_mode";r.message="worker supports input_mode=shared_path only";return r;}std::string rel,error;if(!safe_relative_path(extract_json_string(payload,"local_path"),&rel,&error)){r.code=error;r.message="invalid shared_path local_path";return r;}r.resolved_path=normalize_path(join_path(c.path_base_dir,rel));if(!replace_json_string(&payload,"local_path",r.resolved_path)){r.code="local_path_missing";r.message="payload local_path could not be replaced";return r;}const std::string job_id=extract_json_string(claimed,"job_id"),type=extract_json_string(claimed,"type");std::ostringstream job;job<<"{\"job_id\":\""<<json_escape(job_id)<<"\",\"type\":\""<<json_escape(type)<<"\"";if(payload.size()>=2){auto inner=trim(payload.substr(1,payload.size()-2));if(!inner.empty())job<<","<<inner;}job<<"}";r.ok=true;r.job_json=job.str();return r;}
std::string worker_command(const LoopConfig& c,const std::string& job_path){
#ifdef _WIN32
std::string cmd="call "+shell_quote(c.worker_bin);
#else
std::string cmd=shell_quote(c.worker_bin);
#endif
return cmd+" once --config "+shell_quote(c.config_path)+" --job "+shell_quote(normalize_path(job_path))+" 2>&1";}
std::string result_body(const LoopConfig& c,const std::string& id,const std::string& result){return "{\"worker_id\":\""+json_escape(c.worker_id)+"\",\"job_id\":\""+json_escape(id)+"\",\"result\":"+(result.empty()?"{}":result)+"}";}
std::string fail_body(const LoopConfig& c,const std::string& id,const std::string& code,const std::string& message,const std::string& detail=""){std::string out="{\"worker_id\":\""+json_escape(c.worker_id)+"\",\"job_id\":\""+json_escape(id)+"\",\"error\":{\"code\":\""+json_escape(code)+"\",\"message\":\""+json_escape(message)+"\"";if(!detail.empty()&&detail.find('{')!=std::string::npos)out+=",\"worker_result\":"+detail;return out+"}}";}
bool worker_success(const CommandResult& r){return normalized_exit_code(r.exit_code)==0&&r.output.find("\"processor_execution\": \"completed\"")!=std::string::npos;}
int usage(){std::cout<<"av-imgdata-worker-api-loop "<<AV_IMGDATA_WORKER_VERSION<<"\n\nUsage:\n  av-imgdata-worker-api-loop --config <worker-config.json> [--api-url <url>] [--worker-bin <path>] [--path-base-dir <path>] [--max-iterations <n>]\n\nshared_path jobs require input_mode=shared_path and a relative local_path.\n";return 0;}
}

int main(int argc,char** argv){std::vector<std::string>args;for(int i=1;i<argc;++i)args.push_back(argv[i]);if(args.empty()||has_arg(args,"--help")||has_arg(args,"-h"))return usage();const std::string config_path=arg_value(args,"--config");if(config_path.empty()){std::cerr<<"ERROR: --config is required\n";return 2;}if(!file_exists(config_path)){std::cerr<<"ERROR: config file not found: "<<config_path<<"\n";return 3;}const std::string config_json=read_file(config_path);const LoopConfig c=parse_config(config_path,config_json,args);const int max_iterations=parse_int(arg_value(args,"--max-iterations"),0);if(c.worker_id.empty()||c.api_url.empty()||!file_exists(c.token_file)||!file_exists(c.worker_bin)){std::cerr<<"ERROR: incomplete worker configuration\n";return 4;}const std::string token=read_token(c.token_file);ensure_dir(join_path(c.workspace_root,"claimed-jobs"));int iteration=0;while(max_iterations<=0||iteration<max_iterations){++iteration;const std::string heartbeat=api_post(c,"heartbeat",token,heartbeat_body(c,"ready"));const std::string claim=api_post(c,"claim",token,claim_body(c));const std::string status=extract_json_string(claim,"status");std::cout<<"{\"mode\":\"api-loop\",\"iteration\":"<<iteration<<",\"worker_id\":\""<<json_escape(c.worker_id)<<"\",\"api_url\":\""<<json_escape(c.api_url)<<"\",\"path_base_dir\":\""<<json_escape(c.path_base_dir)<<"\",\"heartbeat_status\":\""<<json_escape(extract_json_string(heartbeat,"status"))<<"\",\"claim_status\":\""<<json_escape(status)<<"\"";if(status=="claimed"){const std::string claimed=extract_object(claim,"job"),id=extract_json_string(claimed,"job_id");const LocalJobResult local=make_local_job(claimed,c);if(!local.ok){api_post(c,"fail",token,fail_body(c,id,local.code,local.message));std::cout<<",\"job_id\":\""<<json_escape(id)<<"\",\"reported\":\"fail\",\"error_code\":\""<<json_escape(local.code)<<"\"";}else{const std::string job_path=normalize_path(join_path(join_path(c.workspace_root,"claimed-jobs"),id+".json"));write_file(job_path,local.job_json);const CommandResult wr=run_command(worker_command(c,job_path));const int exit_code=normalized_exit_code(wr.exit_code);if(worker_success(wr)){api_post(c,"result",token,result_body(c,id,wr.output));std::cout<<",\"job_id\":\""<<json_escape(id)<<"\",\"reported\":\"result\",\"resolved_path\":\""<<json_escape(local.resolved_path)<<"\",\"worker_exit_code\":"<<exit_code;}else{api_post(c,"fail",token,fail_body(c,id,"worker_execution_failed",wr.output,wr.output));std::cout<<",\"job_id\":\""<<json_escape(id)<<"\",\"reported\":\"fail\",\"resolved_path\":\""<<json_escape(local.resolved_path)<<"\",\"worker_exit_code\":"<<exit_code<<",\"worker_output_preview\":\""<<json_escape(abbreviate(wr.output,600))<<"\"";}}}std::cout<<"}"<<std::endl;if(max_iterations>0&&iteration>=max_iterations)break;std::this_thread::sleep_for(std::chrono::seconds(c.poll_interval_seconds));}return 0;}
